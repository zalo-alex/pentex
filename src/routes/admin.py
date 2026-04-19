import secrets
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from sqlalchemy import func
from flask_login import login_required, login_user, current_user
from src.models import db, User, InviteToken, Category, Vulnerability, Report, Log
from src.log import add_log

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
                           categories=categories, logs=logs,
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


@admin_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    if user_id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin_bp.index'))

    user = User.query.get_or_404(user_id)
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


@admin_bp.route('/admin/users/<int:user_id>/change-password', methods=['POST'])
@admin_required
def change_password(user_id):
    user = User.query.get_or_404(user_id)
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


@admin_bp.route('/admin/categories/create', methods=['POST'])
@admin_required
def create_category():
    name = request.form.get('name', '').strip()
    if name and not Category.query.filter_by(name=name).first():
        db.session.add(Category(name=name))
        db.session.commit()
        add_log('CATEGORY_CREATE', detail=name)
    return redirect(url_for('admin_bp.index'))


@admin_bp.route('/admin/categories/<int:cat_id>/delete', methods=['POST'])
@admin_required
def delete_category(cat_id):
    cat = Category.query.get_or_404(cat_id)
    cat_name = cat.name
    Vulnerability.query.filter_by(category_id=cat_id).update({'category_id': None})
    Report.query.filter_by(category_id=cat_id).update({'category_id': None})
    db.session.delete(cat)
    db.session.commit()
    add_log('CATEGORY_DELETE', detail=cat_name)
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
