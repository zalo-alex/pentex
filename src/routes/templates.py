import io
import re
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
from flask import (Blueprint, render_template, jsonify, request, abort, Response, send_file,
                    current_app, send_from_directory, url_for, flash, redirect)
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename
from src.models import db, Template, TemplateVersion, Asset, TranslationRule
from src import template_storage, asset_storage
from src.log import add_log
from src.services.translation import translate_template_page, detect_wording_changes, TranslationError

templates_bp = Blueprint('templates_bp', __name__)


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def analyze_css(content):
    results = []
    static_value_regex = r"(?<![z\d-])(-?\d+(?:\.\d+)?(?:cm|mm|Q|in|pc|pt|px|em|ex|ch|rem|lh|vw|vh|vmin|vmax))"
    for i, line in enumerate(content.splitlines(), 1):
        matches = re.findall(static_value_regex, line)
        if not matches:
            continue

        result = {'line_index': i, 'matches': [], 'line': line, 'message': 'Use var(--z-10px) format instead'}
        for match in matches:
            if match not in result['matches']:
                result['matches'].append(match)

        results.append(result)
    return results

def analyze_hbs(filename, content):
    if filename == "headers.hbs":
        if '<header' not in content:
            return [{
                'line_index': 0,
                'matches': [],
                'line': 'Missing <header>',
                'message': ''
            }]
        elif '<footer' not in content:
            return [{
                'line_index': 0,
                'matches': [],
                'line': 'Missing <footer>',
                'message': ''
            }]
    else:
        if not content.startswith('<page'):
            return [{
                'line_index': 0,
                'matches': [],
                'line': 'Missing <page> at the beginning of the file',
                'message': ''
            }]
    return []

def analyze_template(filename, content):
    if filename.endswith('.css'):
        return analyze_css(content)
    elif filename.endswith('.hbs'):
        return analyze_hbs(filename, content)
    return []

def analyze_templates(pages):
    results = []
    for page in pages:
        result = analyze_template(page['filename'], page['content'])
        page["result"] = result
        results.append(page)
    return results


def _page_dict(page):
    return {'filename': page.filename, 'content': page.content}


def _content_type(filename):
    return 'text/css' if filename.endswith('.css') else 'text/html'


def _version_dict(v):
    return {
        'id': v.public_id,
        'version_number': v.version_number,
        'label': v.label,
        'created_by_username': v.created_by_username,
        'created_at': v.created_at.isoformat() if v.created_at else None,
        'page_count': len(v.pages),
    }


def _human_size(n):
    size = float(n)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024


def _asset_dict(a):
    return {
        'id': a.public_id,
        'filename': a.filename,
        'size_display': _human_size(a.size),
        'is_image': bool(a.content_type) and a.content_type.startswith('image/'),
        'uploaded_by_username': a.uploaded_by_username,
        'created_at': a.created_at.isoformat() if a.created_at else None,
        'url': url_for('templates_bp.serve_asset', asset_id=a.public_id, filename=a.filename),
    }


def _reject_clone(tpl):
    # Per-report private clones are managed only via report create/delete;
    # don't let the template-management surface touch them directly.
    if tpl.is_report_clone:
        abort(404)


@templates_bp.route('/templates')
@login_required
def index():
    # A template's EN sibling is reached via the translate/"View EN version" flow on the
    # editor page, not as an independent entry here — the list represents one bundle per
    # language pair (or unpaired template), not one row per language.
    bundles = (Template.query.filter_by(is_report_clone=False)
               .filter(Template.language != 'EN')
               .order_by(Template.name).all())
    summaries = []
    for tpl in bundles:
        analyzed = analyze_templates([_page_dict(p) for p in tpl.pages])
        error_count = sum(len(p['result']) for p in analyzed)
        summaries.append({
            'id': tpl.public_id,
            'name': tpl.name,
            'is_default': tpl.is_default,
            'page_count': len(tpl.pages),
            'error_count': error_count,
            'version_count': len(tpl.versions),
        })
    assets = [_asset_dict(a) for a in Asset.query.order_by(Asset.created_at.desc()).all()]
    return render_template('templates.html', bundles=summaries, assets=assets,
                            is_admin=current_user.is_admin)


@templates_bp.route('/templates/<string:template_id>')
@login_required
def edit(template_id):
    tpl = Template.query.filter_by(public_id=template_id).first_or_404()
    _reject_clone(tpl)
    pages = analyze_templates([_page_dict(p) for p in tpl.pages])

    translation = None
    if tpl.translation_group_id:
        translation = Template.query.filter(
            Template.translation_group_id == tpl.translation_group_id,
            Template.id != tpl.id,
        ).first()

    return render_template('template_edit.html', template=tpl, pages=pages, translation=translation,
                           is_admin=current_user.is_admin)


def _unique_template_name(base_name, target_language):
    candidate = f'{base_name} ({target_language})'
    suffix = 2
    while Template.query.filter_by(name=candidate).first():
        candidate = f'{base_name} ({target_language}) {suffix}'
        suffix += 1
    return candidate


_template_translate_jobs = {}
_template_translate_jobs_lock = threading.Lock()
_TEMPLATE_TRANSLATE_WORKERS = 4


def _update_template_job(job_id, **kwargs):
    with _template_translate_jobs_lock:
        if job_id in _template_translate_jobs:
            _template_translate_jobs[job_id].update(kwargs)


def _run_template_translate_job(app_obj, job_id, source_public_id, target_language, username, overwrite_target_public_id=None):
    """Runs in a background thread: pages are translated concurrently (each is an independent
    LLM call), and writes only happen if every page translates successfully — never leaving a
    partially-translated template behind. If overwrite_target_public_id is set (re-translating
    an existing pair), the target template's current pages are snapshotted as a new version
    first, so the previous translation is always recoverable, then overwritten in place;
    otherwise a brand new sibling Template is created."""
    with app_obj.app_context():
        tpl = Template.query.filter_by(public_id=source_public_id).first()
        if not tpl or tpl.is_report_clone:
            _update_template_job(job_id, status='error', message='Template not found.')
            return

        source_language = tpl.language or 'FR'
        hbs_pages = [p for p in tpl.pages if p.filename.endswith('.hbs')]
        _update_template_job(job_id, total=len(hbs_pages), message=f'Translating 0 / {len(hbs_pages)} pages…')

        # Captured once up front (not inside the worker threads) so worker threads never touch
        # db.session — matches how hbs_pages/source_language are already captured before the pool.
        rule_texts = [r.text for r in TranslationRule.query.order_by(TranslationRule.created_at.asc()).all()]

        translated = {}
        error = None
        processed = 0

        def _translate(page):
            return page.filename, translate_template_page(page.content, source_language, target_language, rules=rule_texts)

        with ThreadPoolExecutor(max_workers=_TEMPLATE_TRANSLATE_WORKERS) as executor:
            futures = {executor.submit(_translate, p): p for p in hbs_pages}
            for future in as_completed(futures):
                page = futures[future]
                try:
                    filename, content = future.result()
                    translated[filename] = content
                    processed += 1
                    _update_template_job(job_id, processed=processed,
                                         message=f'Translating {processed} / {len(hbs_pages)} pages…')
                except TranslationError as e:
                    error = f'{page.filename}: {e}'

        if error:
            _update_template_job(job_id, status='error', message=f'Translation failed on {error}')
            return

        if overwrite_target_public_id:
            target_tpl = Template.query.filter_by(public_id=overwrite_target_public_id).first()
            if not target_tpl:
                _update_template_job(job_id, status='error', message='The existing translation no longer exists.')
                return

            next_number = (db.session.query(db.func.max(TemplateVersion.version_number))
                           .filter_by(template_id=target_tpl.id).scalar() or 0) + 1
            version = TemplateVersion(
                template_id=target_tpl.id, version_number=next_number,
                label='Auto-saved before re-translation', created_by_username=username,
            )
            db.session.add(version)
            db.session.flush()
            template_storage.snapshot_version(target_tpl.public_id, next_number)
            db.session.commit()

            for filename, content in translated.items():
                template_storage.write_page(target_tpl.public_id, filename, content)
                template_storage.write_baseline_page(target_tpl.public_id, filename, content)

            add_log('TEMPLATE_TRANSLATE', detail=f'{tpl.name} -> {target_tpl.name} (re-translated, prior content saved as v{next_number})', username=username)
            _update_template_job(job_id, status='done', processed=len(hbs_pages),
                                 message=f'Updated "{target_tpl.name}" (previous content saved as version {next_number}).',
                                 redirect=f'/templates/{target_tpl.public_id}')
            return

        group_id = tpl.translation_group_id or str(uuid.uuid4())
        tpl.translation_group_id = group_id

        new_tpl = Template(name=_unique_template_name(tpl.name, target_language), is_default=False,
                           language=target_language, translation_group_id=group_id)
        db.session.add(new_tpl)
        db.session.flush()  # populate new_tpl.public_id before writing to disk

        template_storage.clone_template(tpl.public_id, new_tpl.public_id)
        for filename, content in translated.items():
            template_storage.write_page(new_tpl.public_id, filename, content)
            template_storage.write_baseline_page(new_tpl.public_id, filename, content)

        # clone_template copies the source's page-order file along with everything else, but
        # re-apply it explicitly so the new template's ordering is guaranteed correct even if
        # the source never had one written (e.g. an older template predating page ordering).
        source_order = template_storage.read_page_order(tpl.public_id)
        if source_order:
            template_storage.write_page_order(new_tpl.public_id, source_order)

        db.session.commit()
        add_log('TEMPLATE_TRANSLATE', detail=f'{tpl.name} -> {new_tpl.name}', username=username)
        _update_template_job(job_id, status='done', processed=len(hbs_pages),
                             message=f'Created "{new_tpl.name}".',
                             redirect=f'/templates/{new_tpl.public_id}')


@templates_bp.route('/templates/<string:template_id>/translate/preview-changes')
@admin_required
def translate_template_preview_changes(template_id):
    tpl = Template.query.filter_by(public_id=template_id).first_or_404()
    _reject_clone(tpl)

    target = None
    if tpl.translation_group_id:
        target = Template.query.filter_by(
            translation_group_id=tpl.translation_group_id, language='EN', is_report_clone=False,
        ).first()
    if not target:
        return jsonify({'changes': [], 'pages_without_baseline': []})

    changes = []
    pages_without_baseline = []
    for page in target.pages:
        if not page.filename.endswith('.hbs'):
            continue
        baseline = template_storage.read_baseline_page(target.public_id, page.filename)
        if baseline is None:
            # No baseline captured yet for this page (predates baseline-tracking, or this is
            # the first re-translate since it was introduced) — we genuinely can't tell what
            # was hand-edited, so surface that explicitly instead of silently saying "nothing
            # changed" right before the content gets overwritten.
            pages_without_baseline.append(page.filename)
            continue
        for change in detect_wording_changes(baseline, page.content):
            changes.append({'filename': page.filename, **change})
    return jsonify({'changes': changes, 'pages_without_baseline': pages_without_baseline})


@templates_bp.route('/templates/<string:template_id>/translate', methods=['POST'])
@admin_required
def translate_template(template_id):
    tpl = Template.query.filter_by(public_id=template_id).first_or_404()
    _reject_clone(tpl)

    if (tpl.language or 'FR') == 'EN':
        return jsonify({'error': 'Templates can only be translated from French to English, not the other way around.'}), 400

    target_language = 'EN'
    body = request.get_json(silent=True) or {}
    force = bool(body.get('force'))
    approved_changes = body.get('approved_changes') or []

    if approved_changes:
        created = 0
        for change in approved_changes:
            old, new = (change.get('old') or '').strip(), (change.get('new') or '').strip()
            if not old and not new:
                continue
            if old and new:
                text = f'Use "{new}" instead of "{old}"'
            elif new:
                text = f'Add "{new}"'
            else:
                text = f'Remove "{old}"'
            if TranslationRule.query.filter(db.func.lower(TranslationRule.text) == text.lower()).first():
                continue
            db.session.add(TranslationRule(text=text, source='auto', created_by_id=current_user.id,
                                           created_by_username=current_user.username))
            created += 1
        if created:
            db.session.commit()
            add_log('TRANSLATION_RULE_CREATE', detail=f'{created} rule(s) from re-translate review')

    existing = None
    if tpl.translation_group_id:
        existing = Template.query.filter_by(
            translation_group_id=tpl.translation_group_id, language=target_language, is_report_clone=False,
        ).first()
        if existing and not force:
            return jsonify({'done': True, 'redirect': f'/templates/{existing.public_id}'})

    job_id = str(uuid.uuid4())
    with _template_translate_jobs_lock:
        _template_translate_jobs[job_id] = {
            'status': 'running', 'total': 0, 'processed': 0,
            'message': 'Starting translation…', 'redirect': None,
        }

    app_obj = current_app._get_current_object()
    thread = threading.Thread(
        target=_run_template_translate_job,
        args=(app_obj, job_id, tpl.public_id, target_language, current_user.username,
             existing.public_id if existing else None),
        daemon=True,
    )
    thread.start()

    return jsonify({'job_id': job_id})


@templates_bp.route('/templates/<string:template_id>/translate/<job_id>/status')
@admin_required
def translate_template_status(template_id, job_id):
    with _template_translate_jobs_lock:
        job = _template_translate_jobs.get(job_id)
    if not job:
        abort(404)
    return jsonify(job)


@templates_bp.route('/api/templates')
@login_required
def api_list():
    bundles = Template.query.filter_by(is_report_clone=False).order_by(Template.name).all()
    return jsonify([{'id': t.public_id, 'name': t.name, 'is_default': t.is_default} for t in bundles])


@templates_bp.route('/api/templates/<string:template_id>/pages')
@login_required
def api_list_pages(template_id):
    tpl = Template.query.filter_by(public_id=template_id).first_or_404()
    pages = analyze_templates([_page_dict(p) for p in tpl.pages])
    return jsonify(pages)


_PINNED_PAGE_FILENAMES = ('headers.hbs', 'styles.css')


@templates_bp.route('/api/templates/<string:template_id>/pages/order', methods=['PUT'])
@admin_required
def api_reorder_pages(template_id):
    tpl = Template.query.filter_by(public_id=template_id).first_or_404()
    _reject_clone(tpl)
    data = request.get_json(silent=True) or {}
    order = data.get('order')
    if not isinstance(order, list) or not all(isinstance(f, str) for f in order):
        return jsonify({'error': 'order must be a list of filenames.'}), 400

    existing = [p.filename for p in tpl.pages if p.filename not in _PINNED_PAGE_FILENAMES]
    if len(order) != len(existing) or set(order) != set(existing):
        return jsonify({'error': "order must be a permutation of the template's reorderable pages."}), 400

    template_storage.write_page_order(tpl.public_id, order)

    if tpl.language != 'EN' and tpl.translation_group_id:
        sibling = Template.query.filter_by(
            translation_group_id=tpl.translation_group_id, language='EN', is_report_clone=False,
        ).first()
        if sibling:
            sibling_pages = {p.filename for p in sibling.pages if p.filename not in _PINNED_PAGE_FILENAMES}
            if sibling_pages == set(order):
                template_storage.write_page_order(sibling.public_id, order)

    return jsonify({'order': order})


@templates_bp.route('/api/templates/<string:template_id>/pages/<path:filename>/raw')
@login_required
def api_raw_page(template_id, filename):
    tpl = Template.query.filter_by(public_id=template_id).first_or_404()
    content = template_storage.read_page(tpl.public_id, filename)
    if content is None:
        abort(404)
    return Response(content, mimetype=_content_type(filename))


@templates_bp.route('/api/templates/<string:template_id>/pages/<path:filename>', methods=['PUT'])
@admin_required
def api_update_page(template_id, filename):
    tpl = Template.query.filter_by(public_id=template_id).first_or_404()
    _reject_clone(tpl)
    existing = template_storage.read_page(tpl.public_id, filename)
    if existing is None:
        abort(404)
    data = request.get_json() or {}
    content = data.get('content', existing)
    template_storage.write_page(tpl.public_id, filename, content)
    result = analyze_template(filename, content)
    return jsonify({'filename': filename, 'content': content, 'result': result})


def _rule_dict(r):
    return {
        'id': r.public_id,
        'text': r.text,
        'source': r.source,
        'created_by_username': r.created_by_username,
        'created_at': r.created_at.isoformat() if r.created_at else None,
    }


@templates_bp.route('/api/translation-rules')
@login_required
def api_list_rules():
    rules = TranslationRule.query.order_by(TranslationRule.created_at.asc()).all()
    return jsonify([_rule_dict(r) for r in rules])


@templates_bp.route('/api/translation-rules', methods=['POST'])
@admin_required
def api_create_rule():
    text = ((request.get_json(silent=True) or {}).get('text') or '').strip()
    if not text:
        return jsonify({'error': 'Rule text is required.'}), 400

    existing = TranslationRule.query.filter(db.func.lower(TranslationRule.text) == text.lower()).first()
    if existing:
        return jsonify(_rule_dict(existing)), 200

    rule = TranslationRule(text=text, source='manual', created_by_id=current_user.id,
                           created_by_username=current_user.username)
    db.session.add(rule)
    db.session.commit()
    add_log('TRANSLATION_RULE_CREATE', detail=text[:200])
    return jsonify(_rule_dict(rule)), 201


@templates_bp.route('/api/translation-rules/<string:rule_id>', methods=['DELETE'])
@admin_required
def api_delete_rule(rule_id):
    rule = TranslationRule.query.filter_by(public_id=rule_id).first_or_404()
    text = rule.text
    db.session.delete(rule)
    db.session.commit()
    add_log('TRANSLATION_RULE_DELETE', detail=text[:200])
    return '', 204


@templates_bp.route('/api/templates/<string:template_id>/versions', methods=['POST'])
@admin_required
def api_create_version(template_id):
    tpl = Template.query.filter_by(public_id=template_id).first_or_404()
    _reject_clone(tpl)
    if not tpl.pages:
        return jsonify({'error': 'Template has no pages to snapshot.'}), 400

    data = request.get_json(silent=True) or {}
    label = (data.get('label') or '').strip()[:200] or None

    next_number = (db.session.query(db.func.max(TemplateVersion.version_number))
                   .filter_by(template_id=tpl.id).scalar() or 0) + 1

    version = TemplateVersion(
        template_id=tpl.id,
        version_number=next_number,
        label=label,
        created_by_id=current_user.id,
        created_by_username=current_user.username,
    )
    db.session.add(version)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Version number conflict, please retry.'}), 409

    template_storage.snapshot_version(tpl.public_id, next_number)
    db.session.commit()

    return jsonify(_version_dict(version)), 201


@templates_bp.route('/api/templates/<string:template_id>/versions')
@login_required
def api_list_versions(template_id):
    tpl = Template.query.filter_by(public_id=template_id).first_or_404()
    versions = (TemplateVersion.query.filter_by(template_id=tpl.id)
                .order_by(TemplateVersion.version_number.desc()).all())
    return jsonify([_version_dict(v) for v in versions])


@templates_bp.route('/api/templates/<string:template_id>/versions/<string:version_id>/download')
@login_required
def api_download_version(template_id, version_id):
    tpl = Template.query.filter_by(public_id=template_id).first_or_404()
    version = TemplateVersion.query.filter_by(public_id=version_id, template_id=tpl.id).first_or_404()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for page in version.pages:
            zf.writestr(page.filename, page.content or '')
    buf.seek(0)

    tpl_slug = re.sub(r'[^A-Za-z0-9_-]+', '_', version.template.name).strip('_') or 'template'
    download_name = f'{tpl_slug}_v{version.version_number}.zip'
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name=download_name)


@templates_bp.route('/templates/assets/upload', methods=['POST'])
@admin_required
def upload_asset():
    file = request.files.get('file')
    if not file or not file.filename:
        flash('Please choose a file to upload.', 'error')
        return redirect(url_for('templates_bp.index'))

    filename = secure_filename(file.filename)[:255]
    if not filename:
        flash('That filename is not valid.', 'error')
        return redirect(url_for('templates_bp.index'))

    asset = Asset(filename=filename, content_type=file.mimetype or None, size=0,
                  uploaded_by_id=current_user.id, uploaded_by_username=current_user.username)
    db.session.add(asset)
    db.session.flush()  # populate asset.public_id before writing to disk

    try:
        size = asset_storage.save_asset(asset.public_id, filename, file)
    except ValueError:
        db.session.rollback()
        flash('That filename is not valid.', 'error')
        return redirect(url_for('templates_bp.index'))

    max_size = current_app.config['ASSET_MAX_UPLOAD_SIZE']
    if size > max_size:
        asset_storage.delete_asset(asset.public_id)
        db.session.rollback()
        flash(f'File is too large (max {_human_size(max_size)}).', 'error')
        return redirect(url_for('templates_bp.index'))

    asset.size = size
    db.session.commit()
    add_log('ASSET_UPLOAD', detail=f'{filename} ({_human_size(size)})')
    flash(f'Uploaded "{filename}".', 'info')
    return redirect(url_for('templates_bp.index'))


@templates_bp.route('/templates/assets/<string:asset_id>/delete', methods=['POST'])
@admin_required
def delete_asset(asset_id):
    asset = Asset.query.filter_by(public_id=asset_id).first_or_404()
    filename = asset.filename
    db.session.delete(asset)
    db.session.commit()
    asset_storage.delete_asset(asset_id)
    add_log('ASSET_DELETE', detail=filename)
    flash(f'Deleted "{filename}".', 'info')
    return redirect(url_for('templates_bp.index'))


@templates_bp.route('/templates/assets/<string:asset_id>/<path:filename>')
@login_required
def serve_asset(asset_id, filename):
    asset = Asset.query.filter_by(public_id=asset_id).first_or_404()
    if filename != asset.filename:
        abort(404)
    located = asset_storage.asset_file(asset.public_id, asset.filename)
    if not located:
        abort(404)
    directory, fname = located
    return send_from_directory(directory, fname)
