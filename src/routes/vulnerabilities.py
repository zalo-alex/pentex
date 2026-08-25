import math
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml
from flask import Blueprint, render_template, redirect, url_for, request, jsonify, abort, flash, current_app
from flask_login import login_required, current_user
from markupsafe import escape

from src.models import db, Vulnerability, Category
from src.log import add_log
from src.services.translation import translate_vulnerability_fields, TranslationError

vulnerabilities = Blueprint('vulnerabilities', __name__)

# In-memory PwnDoc-NG import job tracker (job_id -> progress dict), mirroring the
# in-memory collaborative-editing state already kept in app.py. Jobs are ephemeral:
# the process only needs them long enough for the client to poll to completion.
_import_jobs = {}
_import_jobs_lock = threading.Lock()
_TRANSLATE_WORKERS = 8


def _update_job(job_id, **kwargs):
    with _import_jobs_lock:
        if job_id in _import_jobs:
            _import_jobs[job_id].update(kwargs)


_CVSS_WEIGHTS = {
    'AV': {'N': 0.85, 'A': 0.62, 'L': 0.55, 'P': 0.2},
    'AC': {'L': 0.77, 'H': 0.44},
    'PR': {'U': {'N': 0.85, 'L': 0.62, 'H': 0.27}, 'C': {'N': 0.85, 'L': 0.68, 'H': 0.5}},
    'UI': {'N': 0.85, 'R': 0.62},
    'C': {'N': 0, 'L': 0.22, 'H': 0.56},
    'I': {'N': 0, 'L': 0.22, 'H': 0.56},
    'A': {'N': 0, 'L': 0.22, 'H': 0.56},
}

_PRIORITY_MAP = {1: 'Low', 2: 'Medium', 3: 'High', 4: 'Critical'}
_COMPLEXITY_MAP = {1: 'Low', 2: 'Medium', 3: 'High'}


def _parse_cvss_vector(vector):
    m = {'AV': 'N', 'AC': 'L', 'PR': 'N', 'UI': 'N', 'S': 'U', 'C': 'N', 'I': 'N', 'A': 'N'}
    if vector:
        for part in vector.split('/')[1:]:
            k, v = part.split(':')
            m[k] = v
    return m


def _calculate_cvss_score(metrics):
    iss = 1 - ((1 - _CVSS_WEIGHTS['C'][metrics['C']]) * (1 - _CVSS_WEIGHTS['I'][metrics['I']]) * (1 - _CVSS_WEIGHTS['A'][metrics['A']]))
    impact = 6.42 * iss if metrics['S'] == 'U' else 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15
    if impact <= 0:
        return 0.0

    pr_weight = _CVSS_WEIGHTS['PR'][metrics['S']][metrics['PR']]
    exploitability = 8.22 * _CVSS_WEIGHTS['AV'][metrics['AV']] * _CVSS_WEIGHTS['AC'][metrics['AC']] * pr_weight * _CVSS_WEIGHTS['UI'][metrics['UI']]
    score = min(impact + exploitability, 10) if metrics['S'] == 'U' else min(1.08 * (impact + exploitability), 10)
    return math.ceil(score * 10) / 10


def _severity_for_score(score):
    if score == 0:
        return 'NONE'
    if score < 4:
        return 'LOW'
    if score < 7:
        return 'MEDIUM'
    if score < 9:
        return 'HIGH'
    return 'CRITICAL'


def _references_to_html(references):
    items = [str(r).strip() for r in (references or []) if str(r).strip()]
    if not items:
        return ''
    return '<ul>' + ''.join(f'<li>{escape(r)}</li>' for r in items) + '</ul>'


def _get_or_create_category(name):
    name = (name or '').strip()
    if not name:
        return None
    category = Category.query.filter(db.func.lower(Category.name) == name.lower()).first()
    if not category:
        category = Category(name=name)
        db.session.add(category)
        db.session.flush()
    return category


def _build_vuln(content, *, cvss_vector, remediation_priority, remediation_complexity,
                 category_id, language, translation_group_id, created_by_id):
    vuln = Vulnerability(created_by_id=created_by_id)
    vuln.name = (content.get('title') or '').strip() or 'Untitled'
    vuln.description = content.get('description') or ''
    vuln.observation = content.get('observation') or ''
    vuln.remediation = content.get('remediation') or ''
    vuln.classification = content.get('vulnType') or ''
    vuln.references = content.get('references_html', '')
    vuln.category_id = category_id
    vuln.language = language
    vuln.translation_group_id = translation_group_id

    vuln.cvss_vector = cvss_vector or ''
    metrics = _parse_cvss_vector(cvss_vector)
    score = _calculate_cvss_score(metrics)
    vuln.cvss_score = score
    vuln.severity = _severity_for_score(score)
    vuln.remediation_priority = remediation_priority
    vuln.remediation_complexity = remediation_complexity
    return vuln


def _save_vuln(vuln, data):
    vuln.name = data.get('name', '').strip()
    vuln.description = data.get('description', '')
    vuln.observation = data.get('observation', '')
    vuln.references = data.get('references', '')
    vuln.classification = data.get('classification', '').strip()
    category_id = data.get('category_id') or None
    category = Category.query.filter_by(public_id=category_id).first() if category_id else None
    vuln.category_id = category.id if category else None
    vuln.cvss_vector = data.get('cvss_vector', '')
    vuln.cvss_score = float(data.get('cvss_score') or 0)
    vuln.severity = data.get('severity', 'NONE')
    vuln.remediation_complexity = data.get('remediation_complexity', 'Low')
    vuln.remediation_priority = data.get('remediation_priority', 'Low')
    vuln.remediation = data.get('remediation', '')
    vuln.language = data.get('language') or vuln.language or 'FR'


def _vuln_json(v):
    return {
        'id': v.public_id,
        'name': v.name,
        'severity': v.severity,
        'cvss_score': v.cvss_score,
        'cvss_vector': v.cvss_vector or '',
        'classification': v.classification or '',
        'category_id': v.category.public_id if v.category else None,
        'category': v.category.name if v.category else None,
        'description': v.description or '',
        'observation': v.observation or '',
        'references': v.references or '',
        'remediation': v.remediation or '',
        'remediation_complexity': v.remediation_complexity or 'Low',
        'remediation_priority': v.remediation_priority or 'Low',
        'language': v.language or 'FR',
        'translation_group_id': v.translation_group_id,
    }


@vulnerabilities.route('/api/vulnerabilities')
@login_required
def api_list():
    # Vulnerabilities are authored/imported in French by default; pickers (like the
    # report editor's "Add Finding" dialog) should only offer the FR catalog unless
    # asked otherwise, with the EN counterpart available on demand via the translate
    # endpoint below.
    language = (request.args.get('language') or 'FR').upper()
    query = Vulnerability.query.order_by(Vulnerability.name)
    if language != 'ALL':
        query = query.filter_by(language=language)
    return jsonify([_vuln_json(v) for v in query.all()])


@vulnerabilities.route('/api/vulnerabilities', methods=['POST'])
@login_required
def api_create():
    data = request.get_json()
    vuln = Vulnerability(name='', created_by_id=current_user.id)
    _save_vuln(vuln, data)
    db.session.add(vuln)
    db.session.commit()
    add_log('VULN_CREATE', detail=vuln.name)
    return jsonify({'id': vuln.public_id, 'name': vuln.name}), 201


@vulnerabilities.route('/api/vulnerabilities/<string:id>', methods=['PUT'])
@login_required
def api_update(id):
    vuln = Vulnerability.query.filter_by(public_id=id).first_or_404()
    if vuln.created_by_id and vuln.created_by_id != current_user.id and not current_user.is_admin:
        abort(403)
    data = request.get_json()
    _save_vuln(vuln, data)
    db.session.commit()
    add_log('VULN_EDIT', detail=vuln.name)
    return jsonify({'id': vuln.public_id, 'name': vuln.name})


@vulnerabilities.route('/api/vulnerabilities/<string:id>', methods=['DELETE'])
@login_required
def api_delete(id):
    vuln = Vulnerability.query.filter_by(public_id=id).first_or_404()
    if vuln.created_by_id and vuln.created_by_id != current_user.id and not current_user.is_admin:
        abort(403)
    name = vuln.name
    db.session.delete(vuln)
    db.session.commit()
    add_log('VULN_DELETE', detail=name)
    return jsonify({'ok': True})


@vulnerabilities.route('/vulnerabilities')
@login_required
def index():
    items = Vulnerability.query.filter_by(language='FR').order_by(Vulnerability.created_at.desc()).all()
    return render_template('vulnerabilities.html', vulnerabilities=items)


@vulnerabilities.route('/vulnerabilities/new', methods=['GET', 'POST'])
@login_required
def new():
    if request.method == 'POST':
        vuln = Vulnerability(name='', created_by_id=current_user.id)
        _save_vuln(vuln, request.form)
        db.session.add(vuln)
        db.session.commit()
        add_log('VULN_CREATE', detail=vuln.name)
        return redirect(url_for('vulnerabilities.index'))

    categories = Category.query.order_by(Category.name).all()
    return render_template('vulnerabilities/new.html', categories=categories)


@vulnerabilities.route('/vulnerabilities/<string:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    vuln = Vulnerability.query.filter_by(public_id=id).first_or_404()
    if vuln.created_by_id and vuln.created_by_id != current_user.id and not current_user.is_admin:
        abort(403)

    if request.method == 'POST':
        _save_vuln(vuln, request.form)
        db.session.commit()
        add_log('VULN_EDIT', detail=vuln.name)
        return redirect(url_for('vulnerabilities.index'))

    translation = None
    if vuln.translation_group_id:
        translation = Vulnerability.query.filter(
            Vulnerability.translation_group_id == vuln.translation_group_id,
            Vulnerability.id != vuln.id,
        ).first()

    categories = Category.query.order_by(Category.name).all()
    return render_template('vulnerabilities/edit.html', vuln=vuln, translation=translation,
                           cvss=_parse_cvss_vector(vuln.cvss_vector), categories=categories)


def _get_or_create_translation(vuln, created_by_id, force=False):
    """Returns (translated_vuln, created_bool). Reuses an existing paired translation
    if one exists, unless force is set — in which case it's regenerated in place;
    otherwise generates it via the LLM and links the pair."""
    target_language = 'FR' if (vuln.language or 'FR') == 'EN' else 'EN'

    existing = None
    if vuln.translation_group_id:
        existing = Vulnerability.query.filter_by(
            translation_group_id=vuln.translation_group_id, language=target_language
        ).first()
        if existing and not force:
            return existing, False

    source_content = {
        'title': vuln.name,
        'vulnType': vuln.classification or '',
        'description': vuln.description or '',
        'observation': vuln.observation or '',
        'remediation': vuln.remediation or '',
    }
    translated_fields = translate_vulnerability_fields(source_content, vuln.language or 'FR', target_language)
    translated_fields['references_html'] = vuln.references or ''

    if existing:
        existing.name = (translated_fields['title'] or '').strip() or 'Untitled'
        existing.description = translated_fields['description']
        existing.observation = translated_fields['observation']
        existing.references = translated_fields['references_html']
        existing.classification = translated_fields['vulnType']
        existing.remediation = translated_fields['remediation']
        existing.cvss_vector = vuln.cvss_vector or ''
        existing.cvss_score = vuln.cvss_score
        existing.severity = vuln.severity
        existing.remediation_complexity = vuln.remediation_complexity
        existing.remediation_priority = vuln.remediation_priority
        existing.category_id = vuln.category_id
        existing.language = target_language
        db.session.commit()
        add_log('VULN_RETRANSLATE', detail=f'{vuln.name} -> {target_language}')
        return existing, False

    group_id = vuln.translation_group_id or str(uuid.uuid4())
    vuln.translation_group_id = group_id

    new_vuln = _build_vuln(
        translated_fields,
        cvss_vector=vuln.cvss_vector,
        remediation_priority=vuln.remediation_priority,
        remediation_complexity=vuln.remediation_complexity,
        category_id=vuln.category_id,
        language=target_language,
        translation_group_id=group_id,
        created_by_id=created_by_id,
    )
    db.session.add(new_vuln)
    db.session.commit()
    add_log('VULN_TRANSLATE', detail=f'{vuln.name} -> {target_language}')
    return new_vuln, True


@vulnerabilities.route('/api/vulnerabilities/<string:id>/translate', methods=['POST'])
@login_required
def api_translate(id):
    vuln = Vulnerability.query.filter_by(public_id=id).first_or_404()
    if vuln.created_by_id and vuln.created_by_id != current_user.id and not current_user.is_admin:
        abort(403)

    force = bool((request.get_json(silent=True) or {}).get('force'))
    if force and (vuln.language or 'FR') != 'FR':
        abort(400, description='Retranslate can only be initiated from the French version.')

    try:
        result_vuln, created = _get_or_create_translation(vuln, current_user.id, force=force)
    except TranslationError as e:
        return jsonify({'error': str(e)}), 502

    return jsonify({**_vuln_json(result_vuln), 'created': created})


def _run_import_job(app_obj, job_id, entries, user_id, username):
    """Runs in a background thread: direct-import phase is sequential (fast, DB-bound),
    translation phase runs LLM calls concurrently (slow, I/O-bound) since each is an
    independent HTTP request. All DB writes stay on this one thread — the worker pool
    only calls the translation service, which does no DB access."""
    with app_obj.app_context():
        created = translated = failed = processed = 0
        translation_tasks = []

        for entry, by_locale in entries:
            try:
                category = _get_or_create_category(entry.get('category'))
                group_id = str(uuid.uuid4())
                cvss_vector = entry.get('cvssv3') or ''
                priority = _PRIORITY_MAP.get(entry.get('priority'), 'Low')
                complexity = _COMPLEXITY_MAP.get(entry.get('remediationComplexity'), 'Low')
                category_id = category.id if category else None

                for locale, detail in by_locale.items():
                    content = dict(detail)
                    content['references_html'] = _references_to_html(detail.get('references'))
                    vuln = _build_vuln(
                        content, cvss_vector=cvss_vector, remediation_priority=priority,
                        remediation_complexity=complexity, category_id=category_id,
                        language=locale, translation_group_id=group_id, created_by_id=user_id,
                    )
                    db.session.add(vuln)
                    created += 1
                db.session.commit()

                missing = [l for l in ('EN', 'FR') if l not in by_locale]
                if len(by_locale) == 1 and missing:
                    source_locale, source_detail = next(iter(by_locale.items()))
                    translation_tasks.append({
                        'source_locale': source_locale, 'source_detail': source_detail,
                        'target_locale': missing[0], 'category_id': category_id,
                        'cvss_vector': cvss_vector, 'priority': priority, 'complexity': complexity,
                        'group_id': group_id,
                    })
                else:
                    processed += 1
                    _update_job(job_id, processed=processed, created=created,
                                message=f'Imported {processed} / {len(entries)} entries…')
            except Exception:
                db.session.rollback()
                failed += 1
                processed += 1
                _update_job(job_id, processed=processed, failed=failed)

        if translation_tasks:
            _update_job(job_id, message=f'Translating {len(translation_tasks)} entries…')

            def _translate(task):
                fields = translate_vulnerability_fields(task['source_detail'], task['source_locale'], task['target_locale'])
                return task, fields

            with ThreadPoolExecutor(max_workers=_TRANSLATE_WORKERS) as executor:
                futures = [executor.submit(_translate, t) for t in translation_tasks]
                for future in as_completed(futures):
                    processed += 1
                    try:
                        task, translated_fields = future.result()
                        translated_fields['references_html'] = _references_to_html(task['source_detail'].get('references'))
                        vuln = _build_vuln(
                            translated_fields, cvss_vector=task['cvss_vector'], remediation_priority=task['priority'],
                            remediation_complexity=task['complexity'], category_id=task['category_id'],
                            language=task['target_locale'], translation_group_id=task['group_id'], created_by_id=user_id,
                        )
                        db.session.add(vuln)
                        db.session.commit()
                        translated += 1
                    except TranslationError:
                        failed += 1
                    except Exception:
                        db.session.rollback()
                        failed += 1
                    _update_job(job_id, processed=processed, created=created, translated=translated, failed=failed,
                                message=f'Translated {processed - (len(entries) - len(translation_tasks))} / {len(translation_tasks)} entries…')

        add_log('VULN_IMPORT', detail=f'{created} created, {translated} translated, {failed} failed', username=username)
        _update_job(
            job_id, status='done', processed=len(entries), created=created, translated=translated, failed=failed,
            message=f'Import complete: {created} imported, {translated} auto-translated, {failed} failed.',
        )


@vulnerabilities.route('/vulnerabilities/import', methods=['POST'])
@login_required
def import_pwndoc():
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'Please choose a file to import.'}), 400

    try:
        raw = file.stream.read().decode('utf-8')
        data = yaml.safe_load(raw)
    except (yaml.YAMLError, UnicodeDecodeError) as e:
        return jsonify({'error': f'Could not parse file: {e}'}), 400

    if not isinstance(data, list):
        return jsonify({'error': 'Expected a YAML/JSON list of PwnDoc-NG vulnerability entries.'}), 400

    entries = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        by_locale = {}
        for detail in (entry.get('details') or []):
            locale = (detail.get('locale') or '').upper()
            if locale in ('EN', 'FR'):
                by_locale[locale] = detail
        if by_locale:
            entries.append((entry, by_locale))

    if not entries:
        return jsonify({'error': 'No importable EN/FR entries found in that file.'}), 400

    job_id = str(uuid.uuid4())
    with _import_jobs_lock:
        _import_jobs[job_id] = {
            'status': 'running', 'total': len(entries), 'processed': 0,
            'created': 0, 'translated': 0, 'failed': 0, 'message': 'Starting import…',
        }

    app_obj = current_app._get_current_object()
    thread = threading.Thread(
        target=_run_import_job, args=(app_obj, job_id, entries, current_user.id, current_user.username), daemon=True,
    )
    thread.start()

    return jsonify({'job_id': job_id})


@vulnerabilities.route('/vulnerabilities/import/<job_id>/status')
@login_required
def import_status(job_id):
    with _import_jobs_lock:
        job = _import_jobs.get(job_id)
    if not job:
        abort(404)
    return jsonify(job)
