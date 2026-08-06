from flask import Blueprint, render_template, redirect, url_for, request, jsonify, abort
from flask_login import login_required, current_user
from src.models import db, Vulnerability, Category
from src.log import add_log

vulnerabilities = Blueprint('vulnerabilities', __name__)


def _parse_cvss_vector(vector):
    m = {'AV': 'N', 'AC': 'L', 'PR': 'N', 'UI': 'N', 'S': 'U', 'C': 'N', 'I': 'N', 'A': 'N'}
    if vector:
        for part in vector.split('/')[1:]:
            k, v = part.split(':')
            m[k] = v
    return m


def _save_vuln(vuln, data):
    vuln.name = data.get('name', '').strip()
    vuln.description = data.get('description', '')
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


@vulnerabilities.route('/api/vulnerabilities')
@login_required
def api_list():
    items = Vulnerability.query.order_by(Vulnerability.name).all()
    return jsonify([{
        'id': v.public_id,
        'name': v.name,
        'severity': v.severity,
        'cvss_score': v.cvss_score,
        'cvss_vector': v.cvss_vector or '',
        'classification': v.classification or '',
        'category_id': v.category.public_id if v.category else None,
        'category': v.category.name if v.category else None,
        'description': v.description or '',
        'remediation': v.remediation or '',
        'remediation_complexity': v.remediation_complexity or 'Low',
        'remediation_priority': v.remediation_priority or 'Low',
    } for v in items])


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
    items = Vulnerability.query.order_by(Vulnerability.created_at.desc()).all()
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

    categories = Category.query.order_by(Category.name).all()
    return render_template('vulnerabilities/edit.html', vuln=vuln,
                           cvss=_parse_cvss_vector(vuln.cvss_vector), categories=categories)