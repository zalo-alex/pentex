from urllib.parse import urlparse
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from src.models import db, User
from src.log import add_log

auth = Blueprint('auth', __name__)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = User.query.filter_by(username=username).first()
        if user and user.password_hash and user.check_password(password):
            login_user(user, remember=remember)
            add_log('LOGIN', username=user.username)
            next_page = request.args.get('next')
            if next_page and urlparse(next_page).netloc:
                next_page = None
            return redirect(next_page or url_for('index'))

        add_log('LOGIN_FAILED', detail=f'username: {username}', username=username or 'unknown')
        flash('Invalid username or password.', 'error')

    return render_template('auth/login.html')



@auth.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'password':
            current_pw = request.form.get('current_password', '')
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')

            if not current_user.password_hash or not current_user.check_password(current_pw):
                flash('Current password is incorrect.', 'error')
            elif not new_pw:
                flash('New password cannot be empty.', 'error')
            elif len(new_pw) < 12:
                flash('Password must be at least 12 characters.', 'error')
            elif new_pw != confirm_pw:
                flash('Passwords do not match.', 'error')
            else:
                current_user.set_password(new_pw)
                db.session.commit()
                add_log('PASSWORD_CHANGE')
                flash('Password updated.', 'info')

        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html')


@auth.route('/logout')
@login_required
def logout():
    add_log('LOGOUT')
    logout_user()
    return redirect(url_for('auth.login'))
