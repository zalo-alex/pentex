import os
import sys
import argparse
import secrets
import logging
from dotenv import load_dotenv
from flask import Flask, render_template, flash, request, abort, redirect, url_for
from flask_login import LoginManager, login_required, current_user
from flask_migrate import Migrate
from flask_socketio import SocketIO, join_room, emit
from flask_wtf.csrf import CSRFProtect
from src.models import db, User, Report, ReportOwner, Template
from src.routes.auth import auth
from src.routes.reports import reports
from src.routes.vulnerabilities import vulnerabilities
from src.routes.templates import templates_bp
from src.routes.admin import admin_bp

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pentex.db'
app.config['WTF_CSRF_TIME_LIMIT'] = 3600
app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken']
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['ASSET_MAX_UPLOAD_SIZE'] = 20 * 1024 * 1024

csrf = CSRFProtect(app)

db.init_app(app)
migrate = Migrate(app, db)
allowed_origin = os.environ.get('ALLOWED_ORIGIN', 'http://localhost:5000')
socketio = SocketIO(app, cors_allowed_origins=allowed_origin)

login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'


@app.after_request
def set_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


app.register_blueprint(auth)
app.register_blueprint(reports)
app.register_blueprint(vulnerabilities)
app.register_blueprint(templates_bp)
app.register_blueprint(admin_bp)

with app.app_context():
    try:
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin_user = User(username='admin', is_admin=True)
            temp_password = secrets.token_urlsafe(16)
            admin_user.set_password(temp_password)
            db.session.add(admin_user)
            db.session.commit()
            logging.warning(f'[PENTEX] Admin account created. Temporary password: {temp_password}')
    except Exception:
        db.session.rollback()


@app.route('/')
@login_required
def index():
    return redirect(url_for('reports.index'))


@app.route('/reports/<string:report_id>')
@login_required
def editor(report_id):
    report = Report.query.filter_by(public_id=report_id).first_or_404()
    if not ReportOwner.query.filter_by(report_id=report.id, user_id=current_user.id).first():
        abort(403)
    tpl = report.template or Template.query.filter_by(is_default=True).first()
    template_id = tpl.public_id if tpl else None
    return render_template('editor.html', report=report, template_id=template_id)


# ── Collaborative editing ──────────────────────────────────────────────────

# In-memory presence state
# { report_id: { user_id: { id, username, color, page, focused_field, sid } } }
_report_rooms: dict = {}

_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4', '#ec4899', '#84cc16']


def _room_key(report_id: str) -> str:
    return f'report_{report_id}'


def _broadcast_users(report_id: int):
    users = list(_report_rooms.get(report_id, {}).values())
    emit('users_updated', {'users': users}, to=_room_key(report_id))


@socketio.on('join_report')
def handle_join(data):
    if not current_user.is_authenticated:
        return
    report_id = data['report_id']
    with app.app_context():
        report = Report.query.filter_by(public_id=report_id).first()
        if not report or not ReportOwner.query.filter_by(
                report_id=report.id, user_id=current_user.id).first():
            return
    join_room(_room_key(report_id))
    room = _report_rooms.setdefault(report_id, {})
    if current_user.id not in room:
        used = {u['color'] for u in room.values()}
        color = next((c for c in _COLORS if c not in used), _COLORS[len(room) % len(_COLORS)])
        room[current_user.id] = {
            'id': current_user.public_id,
            'username': current_user.username,
            'color': color,
            'page': 'general',
            'focused_field': None,
            'sid': request.sid,
        }
    else:
        # Reconnect: update sid, keep color
        room[current_user.id]['sid'] = request.sid
    _broadcast_users(report_id)


@socketio.on('page_change')
def handle_page_change(data):
    if not current_user.is_authenticated:
        return
    report_id = data['report_id']
    room = _report_rooms.get(report_id, {})
    if current_user.id in room:
        room[current_user.id]['page'] = data.get('page', 'general')
        _broadcast_users(report_id)


@socketio.on('field_focus')
def handle_field_focus(data):
    if not current_user.is_authenticated:
        return
    report_id = data['report_id']
    room = _report_rooms.get(report_id, {})
    if current_user.id in room:
        room[current_user.id]['focused_field'] = data.get('field_id')
        _broadcast_users(report_id)


@socketio.on('field_blur')
def handle_field_blur(data):
    if not current_user.is_authenticated:
        return
    report_id = data['report_id']
    room = _report_rooms.get(report_id, {})
    if current_user.id in room:
        room[current_user.id]['focused_field'] = None
        _broadcast_users(report_id)


@socketio.on('field_change')
def handle_field_change(data):
    if not current_user.is_authenticated:
        return
    report_id = data['report_id']
    if report_id not in _report_rooms or current_user.id not in _report_rooms[report_id]:
        return
    socketio.emit('field_changed', data, to=_room_key(report_id), skip_sid=request.sid)


@socketio.on('disconnect')
def handle_disconnect():
    if not current_user.is_authenticated:
        return
    for report_id, room in list(_report_rooms.items()):
        if current_user.id in room:
            del room[current_user.id]
            if not room:
                del _report_rooms[report_id]
            else:
                emit('users_updated', {'users': list(room.values())},
                     to=_room_key(report_id))
            break


def _reset_admin_password():
    with app.app_context():
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            print('[PENTEX] No admin account found.')
            sys.exit(1)
        new_password = secrets.token_urlsafe(16)
        admin_user.set_password(new_password)
        db.session.commit()
        print(f'[PENTEX] Admin password reset. New password: {new_password}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--reset-admin-password', action='store_true',
                         help='Reset the admin account password to a new random value and exit.')
    args = parser.parse_args()

    if args.reset_admin_password:
        _reset_admin_password()
        sys.exit(0)

    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    socketio.run(app, host="0.0.0.0", debug=debug)
