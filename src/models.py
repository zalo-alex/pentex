import uuid
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_auditor = db.Column(db.Boolean, default=False, nullable=False)
    full_name = db.Column(db.String(200), nullable=True)
    email = db.Column(db.String(200), nullable=True)

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


class Template(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), unique=True, nullable=False)
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    versions = db.relationship('TemplateVersion', backref='template', cascade='all, delete-orphan')

    @property
    def pages(self):
        # Page content lives on disk (instance/template_pages/<public_id>/current/);
        # the DB only tracks the template bundle itself.
        from src.template_storage import template_pages
        return template_pages(self.public_id)


class TemplateVersion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    template_id = db.Column(db.Integer, db.ForeignKey('template.id'), nullable=False)
    version_number = db.Column(db.Integer, nullable=False)
    label = db.Column(db.String(200), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    created_by_username = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('template_id', 'version_number'),)

    @property
    def pages(self):
        # Snapshot content lives on disk (instance/template_pages/<public_id>/versions/<n>/);
        # the DB only tracks version metadata.
        from src.template_storage import version_pages
        return version_pages(self.template.public_id, self.version_number)


class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    filename = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(127), nullable=True)
    size = db.Column(db.Integer, nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    uploaded_by_username = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Category(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    name      = db.Column(db.String(100), unique=True, nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('template.id'), nullable=True)
    template = db.relationship('Template', foreign_keys=[template_id])


class ReportOwner(db.Model):
    __tablename__ = 'report_owner'
    report_id = db.Column(db.Integer, db.ForeignKey('report.id'), primary_key=True)
    user_id   = db.Column(db.Integer, db.ForeignKey('user.id'),   primary_key=True)


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    client = db.Column(db.String(200))
    content = db.Column(db.Text)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    template_id = db.Column(db.Integer, db.ForeignKey('template.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    owners   = db.relationship('User',     secondary='report_owner', lazy='joined')
    category = db.relationship('Category', foreign_keys=[category_id])
    template = db.relationship('Template', foreign_keys=[template_id])


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
    public_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
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
