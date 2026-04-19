from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class InviteToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Category(db.Model):
    id   = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)


class ReportOwner(db.Model):
    __tablename__ = 'report_owner'
    report_id = db.Column(db.Integer, db.ForeignKey('report.id'), primary_key=True)
    user_id   = db.Column(db.Integer, db.ForeignKey('user.id'),   primary_key=True)


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    client = db.Column(db.String(200))
    content = db.Column(db.Text)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    owners   = db.relationship('User',     secondary='report_owner', lazy='joined')
    category = db.relationship('Category', foreign_keys=[category_id])


class Log(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    username   = db.Column(db.String(64), nullable=False)
    action     = db.Column(db.String(50), nullable=False)
    detail     = db.Column(db.String(500))
    ip         = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Vulnerability(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    classification = db.Column(db.String(200))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    cvss_vector = db.Column(db.String(100))
    cvss_score = db.Column(db.Float, default=0.0)
    severity = db.Column(db.String(20), default='NONE')
    remediation_complexity = db.Column(db.String(20), default='Low')
    remediation_priority = db.Column(db.String(20), default='Low')
    remediation = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.relationship('Category', foreign_keys=[category_id])
