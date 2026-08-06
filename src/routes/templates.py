import io
import re
import zipfile
from functools import wraps
from flask import (Blueprint, render_template, jsonify, request, abort, Response, send_file,
                    current_app, send_from_directory, url_for, flash, redirect)
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename
from src.models import db, Template, TemplateVersion, Asset
from src import template_storage, asset_storage
from src.log import add_log

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


@templates_bp.route('/templates')
@login_required
def index():
    bundles = Template.query.order_by(Template.name).all()
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
    pages = analyze_templates([_page_dict(p) for p in tpl.pages])
    return render_template('template_edit.html', template=tpl, pages=pages, is_admin=current_user.is_admin)


@templates_bp.route('/api/templates')
@login_required
def api_list():
    bundles = Template.query.order_by(Template.name).all()
    return jsonify([{'id': t.public_id, 'name': t.name, 'is_default': t.is_default} for t in bundles])


@templates_bp.route('/api/templates/<string:template_id>/pages')
@login_required
def api_list_pages(template_id):
    tpl = Template.query.filter_by(public_id=template_id).first_or_404()
    pages = analyze_templates([_page_dict(p) for p in tpl.pages])
    return jsonify(pages)


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
    existing = template_storage.read_page(tpl.public_id, filename)
    if existing is None:
        abort(404)
    data = request.get_json() or {}
    content = data.get('content', existing)
    template_storage.write_page(tpl.public_id, filename, content)
    result = analyze_template(filename, content)
    return jsonify({'filename': filename, 'content': content, 'result': result})


@templates_bp.route('/api/templates/<string:template_id>/versions', methods=['POST'])
@admin_required
def api_create_version(template_id):
    tpl = Template.query.filter_by(public_id=template_id).first_or_404()
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
