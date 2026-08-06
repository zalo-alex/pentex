import secrets
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from sqlalchemy import func
from flask_login import login_required, login_user, current_user
from src.models import db, User, InviteToken, Category, Vulnerability, Report, Log, Template
from src.log import add_log
from src import template_storage

admin_bp = Blueprint('admin_bp', __name__)


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/admin')
@admin_required
def index():
    users = User.query.order_by(User.id).all()
    subq = (db.session.query(InviteToken.user_id, func.max(InviteToken.id).label('max_id'))
            .filter(InviteToken.used == False)
            .group_by(InviteToken.user_id).subquery())
    rows = (db.session.query(InviteToken.user_id, InviteToken.token)
            .join(subq, InviteToken.id == subq.c.max_id).all())
    pending_invites = {r.user_id: r.token for r in rows}
    categories = Category.query.order_by(Category.name).all()
    templates = Template.query.order_by(Template.name).all()

    log_page   = max(1, request.args.get('log_page', 1, type=int))
    log_action = request.args.get('log_action', '').strip()
    log_user   = request.args.get('log_user', '').strip()
    per_page   = 50

    log_q = Log.query
    if log_action:
        log_q = log_q.filter(Log.action == log_action)
    if log_user:
        log_q = log_q.filter(Log.username.ilike(f'%{log_user}%'))

    log_total  = log_q.count()
    log_pages  = max(1, (log_total + per_page - 1) // per_page)
    log_page   = min(log_page, log_pages)
    logs       = log_q.order_by(Log.created_at.desc()) \
                      .offset((log_page - 1) * per_page).limit(per_page).all()
    log_actions = [r[0] for r in
                   db.session.query(Log.action).distinct().order_by(Log.action).all()]

    return render_template('admin/index.html', users=users, pending_invites=pending_invites,
                           categories=categories, templates=templates, logs=logs,
                           log_page=log_page, log_pages=log_pages, log_total=log_total,
                           log_action=log_action, log_user=log_user, log_actions=log_actions)


@admin_bp.route('/admin/users/create', methods=['POST'])
@admin_required
def create_user():
    username = request.form.get('username', '').strip()
    if not username:
        flash('Username is required.', 'error')
        return redirect(url_for('admin_bp.index'))

    if User.query.filter_by(username=username).first():
        flash('Username already taken.', 'error')
        return redirect(url_for('admin_bp.index'))

    user = User(username=username)
    db.session.add(user)
    db.session.flush()  # get user.id before commit

    token_value = secrets.token_urlsafe(32)
    invite = InviteToken(token=token_value, user_id=user.id)
    db.session.add(invite)
    db.session.commit()
    add_log('USER_CREATE', detail=username)

    invite_url = url_for('admin_bp.set_password', token=token_value, _external=True)
    flash(f'User "{username}" created.', 'info')
    flash(invite_url, 'invite')
    return redirect(url_for('admin_bp.index'))


@admin_bp.route('/admin/users/<string:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    if user_id == current_user.public_id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin_bp.index'))

    user = User.query.filter_by(public_id=user_id).first_or_404()
    if user.is_admin:
        flash('Cannot delete another admin.', 'error')
        return redirect(url_for('admin_bp.index'))

    deleted_username = user.username
    InviteToken.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    add_log('USER_DELETE', detail=deleted_username)
    flash(f'User "{deleted_username}" deleted.', 'info')
    return redirect(url_for('admin_bp.index'))


@admin_bp.route('/admin/users/<string:user_id>/change-password', methods=['POST'])
@admin_required
def change_password(user_id):
    user = User.query.filter_by(public_id=user_id).first_or_404()
    password = request.form.get('password', '')
    confirm = request.form.get('confirm', '')

    if not password:
        flash('Password is required.', 'error')
    elif len(password) < 12:
        flash('Password must be at least 12 characters.', 'error')
    elif password != confirm:
        flash('Passwords do not match.', 'error')
    else:
        user.set_password(password)
        db.session.commit()
        add_log('PASSWORD_RESET', detail=user.username)
        flash(f'Password updated for "{user.username}".', 'info')

    return redirect(url_for('admin_bp.index'))


@admin_bp.route('/admin/users/<string:user_id>/toggle-auditor', methods=['POST'])
@admin_required
def toggle_auditor(user_id):
    user = User.query.filter_by(public_id=user_id).first_or_404()
    user.is_auditor = not user.is_auditor
    db.session.commit()
    add_log('AUDITOR_TOGGLE', detail=f'{user.username} -> {user.is_auditor}')
    flash(f'{"Marked" if user.is_auditor else "Unmarked"} "{user.username}" as auditor.', 'info')
    return redirect(url_for('admin_bp.index'))


@admin_bp.route('/admin/users/<string:user_id>/profile', methods=['POST'])
@admin_required
def update_profile(user_id):
    user = User.query.filter_by(public_id=user_id).first_or_404()
    user.full_name = request.form.get('full_name', '').strip() or None
    user.email = request.form.get('email', '').strip() or None
    db.session.commit()
    add_log('USER_PROFILE_UPDATE', detail=user.username)
    flash(f'Profile updated for "{user.username}".', 'info')
    return redirect(url_for('admin_bp.index'))


@admin_bp.route('/admin/categories/create', methods=['POST'])
@admin_required
def create_category():
    name = request.form.get('name', '').strip()
    template_public_id = request.form.get('template_id') or None
    template = Template.query.filter_by(public_id=template_public_id).first() if template_public_id else None
    if name and not Category.query.filter_by(name=name).first():
        db.session.add(Category(name=name, template_id=template.id if template else None))
        db.session.commit()
        add_log('CATEGORY_CREATE', detail=name)
    return redirect(url_for('admin_bp.index'))


@admin_bp.route('/admin/categories/<string:cat_id>/delete', methods=['POST'])
@admin_required
def delete_category(cat_id):
    cat = Category.query.filter_by(public_id=cat_id).first_or_404()
    cat_name = cat.name
    Vulnerability.query.filter_by(category_id=cat.id).update({'category_id': None})
    Report.query.filter_by(category_id=cat.id).update({'category_id': None})
    db.session.delete(cat)
    db.session.commit()
    add_log('CATEGORY_DELETE', detail=cat_name)
    return redirect(url_for('admin_bp.index'))


@admin_bp.route('/admin/categories/<string:cat_id>/set-template', methods=['POST'])
@admin_required
def set_category_template(cat_id):
    cat = Category.query.filter_by(public_id=cat_id).first_or_404()
    template_public_id = request.form.get('template_id') or None
    template = None
    if template_public_id:
        template = Template.query.filter_by(public_id=template_public_id).first_or_404()
    cat.template_id = template.id if template else None
    db.session.commit()
    add_log('CATEGORY_SET_TEMPLATE', detail=f'{cat.name} -> {template.name if template else None}')
    return redirect(url_for('admin_bp.index'))


@admin_bp.route('/admin/templates/create', methods=['POST'])
@admin_required
def create_template():
    name = request.form.get('name', '').strip()
    source = Template.query.filter_by(public_id=request.form.get('source_template_id')).first_or_404()

    if not name or Template.query.filter_by(name=name).first():
        flash('Template name is required and must be unique.', 'error')
        return redirect(url_for('admin_bp.index'))

    tpl = Template(name=name, is_default=False)
    db.session.add(tpl)
    db.session.flush()  # get tpl.public_id before commit
    template_storage.clone_template(source.public_id, tpl.public_id)
    db.session.commit()
    add_log('TEMPLATE_CREATE', detail=f'{name} (cloned from {source.name})')
    return redirect(url_for('admin_bp.index'))


@admin_bp.route('/admin/templates/<string:tpl_id>/delete', methods=['POST'])
@admin_required
def delete_template(tpl_id):
    tpl = Template.query.filter_by(public_id=tpl_id).first_or_404()
    if tpl.is_default:
        flash('Cannot delete the default template.', 'error')
        return redirect(url_for('admin_bp.index'))

    default_tpl = Template.query.filter_by(is_default=True).first()
    tpl_name = tpl.name
    tpl_public_id = tpl.public_id
    Category.query.filter_by(template_id=tpl.id).update({'template_id': default_tpl.id if default_tpl else None})
    Report.query.filter_by(template_id=tpl.id).update({'template_id': default_tpl.id if default_tpl else None})
    db.session.delete(tpl)
    db.session.commit()
    template_storage.delete_template(tpl_public_id)
    add_log('TEMPLATE_DELETE', detail=tpl_name)
    return redirect(url_for('admin_bp.index'))


@admin_bp.route('/invite/<token>', methods=['GET', 'POST'])
def set_password(token):
    invite = InviteToken.query.filter_by(token=token, used=False).first_or_404()
    user = User.query.get_or_404(invite.user_id)

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')

        if not password:
            flash('Password is required.', 'error')
        elif len(password) < 12:
            flash('Password must be at least 12 characters.', 'error')
        elif password != confirm:
            flash('Passwords do not match.', 'error')
        else:
            user.set_password(password)
            invite.used = True
            db.session.commit()
            login_user(user)
            return redirect(url_for('index'))

    return render_template('auth/set_password.html', user=user)
