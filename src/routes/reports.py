from flask import Blueprint, render_template, request, jsonify, abort
from flask_login import login_required, current_user
from src.models import db, Report, ReportOwner, User, Category
from src.log import add_log

reports = Blueprint('reports', __name__)


def _is_owner(report):
    return ReportOwner.query.filter_by(
        report_id=report.id, user_id=current_user.id
    ).first() is not None


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
@login_required
def api_create():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    report = Report(user_id=current_user.id, name=name,
                    category_id=data.get('category_id') or None)
    db.session.add(report)
    db.session.flush()  # get report.id before commit
    db.session.add(ReportOwner(report_id=report.id, user_id=current_user.id))
    db.session.commit()
    add_log('REPORT_CREATE', detail=report.name)
    return jsonify({'id': report.id, 'name': report.name}), 201


@reports.route('/api/reports/<int:id>')
@login_required
def api_get(id):
    report = Report.query.get_or_404(id)
    if not _is_owner(report):
        abort(403)
    return jsonify({
        'id': report.id,
        'name': report.name,
        'content': report.content,
        'category_id': report.category_id,
    })


@reports.route('/api/reports/<int:id>', methods=['PUT'])
@login_required
def api_update(id):
    report = Report.query.get_or_404(id)
    if not _is_owner(report):
        abort(403)

    data = request.get_json()
    if 'name' in data:
        report.name = data['name']
    if 'content' in data:
        report.content = data['content']
    if 'category_id' in data:
        report.category_id = data['category_id'] or None
    db.session.commit()
    return jsonify({'id': report.id, 'name': report.name})


@reports.route('/api/reports/<int:id>', methods=['DELETE'])
@login_required
def api_delete(id):
    report = Report.query.get_or_404(id)
    if not _is_owner(report):
        abort(403)
    name = report.name
    db.session.delete(report)
    db.session.commit()
    add_log('REPORT_DELETE', detail=name)
    return jsonify({'ok': True})


# --- Owner management ---

@reports.route('/api/reports/<int:id>/owners')
@login_required
def api_get_owners(id):
    report = Report.query.get_or_404(id)
    if not _is_owner(report):
        abort(403)
    owners = [{'id': u.id, 'username': u.username} for u in report.owners]
    return jsonify(owners)


@reports.route('/api/reports/<int:id>/owners', methods=['POST'])
@login_required
def api_add_owner(id):
    report = Report.query.get_or_404(id)
    if not _is_owner(report):
        abort(403)

    data = request.get_json()
    username = (data.get('username') or '').strip()
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404

    existing = ReportOwner.query.filter_by(report_id=id, user_id=user.id).first()
    if existing:
        return jsonify({'error': 'Already an owner'}), 409

    db.session.add(ReportOwner(report_id=id, user_id=user.id))
    db.session.commit()
    return jsonify({'id': user.id, 'username': user.username}), 201


@reports.route('/api/reports/<int:id>/owners/<int:user_id>', methods=['DELETE'])
@login_required
def api_remove_owner(id, user_id):
    report = Report.query.get_or_404(id)
    if not _is_owner(report):
        abort(403)

    owner_count = ReportOwner.query.filter_by(report_id=id).count()
    if owner_count <= 1:
        return jsonify({'error': 'Cannot remove the last owner'}), 400

    entry = ReportOwner.query.filter_by(report_id=id, user_id=user_id).first()
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
    return jsonify([{'id': u.id, 'username': u.username} for u in users])
