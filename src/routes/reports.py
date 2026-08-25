import io
import json
import uuid
from datetime import date
from functools import wraps

from flask import Blueprint, render_template, request, jsonify, abort, send_file, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from src.models import db, Report, ReportOwner, User, Category, Template
from src.log import add_log
from src.pdf_export import render_html_to_pdf
from src import template_storage

reports = Blueprint('reports', __name__)


def _is_owner(report):
    return ReportOwner.query.filter_by(
        report_id=report.id, user_id=current_user.id
    ).first() is not None


def auditor_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_auditor:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _resolve_template(category, language='FR'):
    """A category points at one Template row, but that row represents a FR/EN pair (linked via
    translation_group_id) rather than a single-language template. Resolve to whichever sibling
    matches the report's language, falling back to the category's own template (untranslated)
    if no matching-language sibling exists yet."""
    base = category.template if (category and category.template) else Template.query.filter_by(is_default=True).first()
    if not base:
        return None, False
    if (base.language or 'FR') == language:
        return base, True
    if base.translation_group_id:
        match = Template.query.filter_by(
            translation_group_id=base.translation_group_id, language=language, is_report_clone=False,
        ).first()
        if match:
            return match, True
    return base, False


def _default_report_content(user, template):
    author = user.full_name or user.username
    today = date.today().strftime('%Y-%m-%d')
    data_store = {
        "global": {
            "clientName": "Example",
            "testType": "Web",
            "approaches": [],
            "blackbox": False,
            "graybox": False,
            "whitebox": False,
            "reference": "",
            "revision": "1.0",
            "abbreviations": [],
            "auditors": [
                {"userId": user.public_id, "fullName": author, "email": user.email or ""}
            ],
            "scopes": [],
            "testAccess": [],
            "diffusionTable": [
                {"company": "", "name": author, "role": "Auditor", "email": user.email or ""}
            ],
            "versionHistory": [
                {
                    "version": "1.0",
                    "date": today,
                    "author": author,
                    "changes": "Initial version",
                    "description": "",
                }
            ],
        },
        "pages": {"findings": []},
    }
    pages_count = {
        p.filename.rsplit('.', 1)[0]: (0 if p.filename.startswith('findings.') else 1)
        for p in template.pages if p.filename not in ('headers.hbs', 'styles.css')
    }
    return json.dumps({"dataStore": data_store, "pagesCount": pages_count, "templates": {}})


@reports.route('/reports')
@login_required
def index():
    items = (Report.query
             .join(ReportOwner, ReportOwner.report_id == Report.id)
             .filter(ReportOwner.user_id == current_user.id)
             .order_by(Report.created_at.desc())
             .all())
    categories = Category.query.order_by(Category.name).all()
    return render_template('reports.html', reports=items, categories=categories)


@reports.route('/api/reports', methods=['POST'])
@auditor_required
def api_create():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    language = (data.get('language') or 'FR').upper()
    if language not in ('FR', 'EN'):
        language = 'FR'

    category_id = data.get('category_id') or None
    category = Category.query.filter_by(public_id=category_id).first() if category_id else None
    source_template, language_matched = _resolve_template(category, language)

    template = source_template
    if source_template:
        template = Template(name=f'__report_clone__{uuid.uuid4().hex}',
                            is_default=False, is_report_clone=True)
        db.session.add(template)
        db.session.flush()  # get template.public_id before it's used as a disk path
        template_storage.clone_template(source_template.public_id, template.public_id)

    report = Report(user_id=current_user.id, name=name,
                    category_id=category.id if category else None,
                    template_id=template.id if template else None,
                    language=language,
                    content=_default_report_content(current_user, template))
    db.session.add(report)
    db.session.flush()  # get report.id before commit
    db.session.add(ReportOwner(report_id=report.id, user_id=current_user.id))
    db.session.commit()
    add_log('REPORT_CREATE', detail=report.name)

    result = {'id': report.public_id, 'name': report.name}
    if source_template and not language_matched:
        result['warning'] = (
            f'No {language} version of "{source_template.name}" exists yet — used the '
            f'{source_template.language} template instead. Translate it from the template editor to fix this.'
        )
    return jsonify(result), 201


@reports.route('/api/reports/<string:id>')
@login_required
def api_get(id):
    report = Report.query.filter_by(public_id=id).first_or_404()
    if not _is_owner(report):
        abort(403)
    return jsonify({
        'id': report.public_id,
        'name': report.name,
        'content': report.content,
        'category_id': report.category.public_id if report.category else None,
        'language': report.language or 'FR',
    })


@reports.route('/api/reports/<string:id>/export/pdf', methods=['POST'])
@login_required
def api_export_pdf(id):
    report = Report.query.filter_by(public_id=id).first_or_404()
    if not _is_owner(report):
        abort(403)

    data = request.get_json(silent=True) or {}
    html = data.get('html')
    if not html or not isinstance(html, str):
        return jsonify({'error': 'html is required'}), 400

    try:
        pdf_bytes = render_html_to_pdf(html)
    except Exception:
        current_app.logger.exception('PDF export failed for report %s', report.public_id)
        return jsonify({'error': 'PDF generation failed'}), 500

    add_log('REPORT_EXPORT_PDF', detail=report.name)
    buf = io.BytesIO(pdf_bytes)
    filename = f'{secure_filename(report.name) or "report"}.pdf'
    return send_file(buf, mimetype='application/pdf', as_attachment=True, download_name=filename)


@reports.route('/api/reports/<string:id>', methods=['PUT'])
@login_required
def api_update(id):
    report = Report.query.filter_by(public_id=id).first_or_404()
    if not _is_owner(report):
        abort(403)

    data = request.get_json()
    if 'name' in data:
        report.name = data['name']
    if 'content' in data:
        report.content = data['content']
    if 'category_id' in data:
        category_id = data['category_id'] or None
        category = Category.query.filter_by(public_id=category_id).first() if category_id else None
        report.category_id = category.id if category else None
    if 'language' in data:
        language = (data['language'] or 'FR').upper()
        report.language = language if language in ('FR', 'EN') else 'FR'
    db.session.commit()
    return jsonify({'id': report.public_id, 'name': report.name})


@reports.route('/api/reports/<string:id>', methods=['DELETE'])
@login_required
def api_delete(id):
    report = Report.query.filter_by(public_id=id).first_or_404()
    if not _is_owner(report):
        abort(403)
    name = report.name
    clone = report.template if (report.template and report.template.is_report_clone) else None
    clone_public_id = clone.public_id if clone else None

    db.session.delete(report)
    if clone:
        db.session.delete(clone)
    db.session.commit()

    if clone_public_id:
        template_storage.delete_template(clone_public_id)
    add_log('REPORT_DELETE', detail=name)
    return jsonify({'ok': True})


# --- Owner management ---

@reports.route('/api/reports/<string:id>/owners')
@login_required
def api_get_owners(id):
    report = Report.query.filter_by(public_id=id).first_or_404()
    if not _is_owner(report):
        abort(403)
    owners = [{'id': u.public_id, 'username': u.username} for u in report.owners]
    return jsonify(owners)


@reports.route('/api/reports/<string:id>/owners', methods=['POST'])
@login_required
def api_add_owner(id):
    report = Report.query.filter_by(public_id=id).first_or_404()
    if not _is_owner(report):
        abort(403)

    data = request.get_json()
    username = (data.get('username') or '').strip()
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    existing = ReportOwner.query.filter_by(report_id=report.id, user_id=user.id).first()
    if existing:
        return jsonify({'error': 'Already an owner'}), 409

    db.session.add(ReportOwner(report_id=report.id, user_id=user.id))
    db.session.commit()
    return jsonify({'id': user.public_id, 'username': user.username}), 201


@reports.route('/api/reports/<string:id>/owners/<string:user_id>', methods=['DELETE'])
@login_required
def api_remove_owner(id, user_id):
    report = Report.query.filter_by(public_id=id).first_or_404()
    if not _is_owner(report):
        abort(403)
    user = User.query.filter_by(public_id=user_id).first_or_404()

    owner_count = ReportOwner.query.filter_by(report_id=report.id).count()
    if owner_count <= 1:
        return jsonify({'error': 'Cannot remove the last owner'}), 400

    entry = ReportOwner.query.filter_by(report_id=report.id, user_id=user.id).first()
    if not entry:
        abort(404)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({'ok': True})


# --- User lookup (for add-owner UI) ---

@reports.route('/api/users')
@login_required
def api_users():
    users = User.query.order_by(User.username).all()
    return jsonify([{'id': u.public_id, 'username': u.username} for u in users])


@reports.route('/api/users/auditors')
@login_required
def api_auditor_users():
    users = User.query.filter_by(is_auditor=True).order_by(User.full_name, User.username).all()
    return jsonify([
        {'id': u.public_id, 'username': u.username, 'full_name': u.full_name, 'email': u.email}
        for u in users
    ])
