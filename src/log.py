from flask import request
from flask_login import current_user
from src.models import db, Log


def add_log(action, detail=None, username=None):
    uid, uname = None, username or 'anonymous'
    try:
        if current_user and current_user.is_authenticated:
            uid   = current_user.id
            uname = current_user.username
    except Exception:
        pass

    try:
        ip = request.remote_addr
    except Exception:
        ip = None

    entry = Log(
        user_id=uid,
        username=uname,
        action=action,
        detail=detail,
        ip=ip,
    )
    try:
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()
