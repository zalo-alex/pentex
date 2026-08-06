"""move template/version page content from DB to disk-backed files

Revision ID: e7a4c8b2f915
Revises: d8f3a6c1b204
Create Date: 2026-07-22 00:00:00.000000

"""
import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector
from flask import current_app


# revision identifiers, used by Alembic.
revision = 'e7a4c8b2f915'
down_revision = 'd8f3a6c1b204'
branch_labels = None
depends_on = None


def _root_dir():
    return os.path.join(current_app.instance_path, 'template_pages')


def _write(directory, filename, content):
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, filename), 'w', encoding='utf-8') as f:
        f.write(content or '')


def upgrade():
    conn = op.get_bind()

    template_public_id = {row[0]: row[1] for row in
                           conn.execute(sa.text("SELECT id, public_id FROM template")).fetchall()}

    pages = conn.execute(sa.text("SELECT template_id, filename, content FROM template_page")).fetchall()
    for template_id, filename, content in pages:
        public_id = template_public_id.get(template_id)
        if not public_id:
            continue
        directory = os.path.join(_root_dir(), public_id, 'current')
        _write(directory, filename, content)

    version_info = {row[0]: (row[1], row[2]) for row in
                     conn.execute(sa.text("SELECT id, template_id, version_number FROM template_version")).fetchall()}

    version_pages = conn.execute(
        sa.text("SELECT template_version_id, filename, content FROM template_version_page")
    ).fetchall()
    for template_version_id, filename, content in version_pages:
        info = version_info.get(template_version_id)
        if not info:
            continue
        template_id, version_number = info
        public_id = template_public_id.get(template_id)
        if not public_id:
            continue
        directory = os.path.join(_root_dir(), public_id, 'versions', str(version_number))
        _write(directory, filename, content)

    op.drop_table('template_version_page')
    op.drop_table('template_page')


def downgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing = inspector.get_table_names()

    if 'template_page' not in existing:
        op.create_table('template_page',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('template_id', sa.Integer(), nullable=False),
            sa.Column('filename', sa.String(200), nullable=False),
            sa.Column('content', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['template_id'], ['template.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('template_id', 'filename'),
        )

    if 'template_version_page' not in existing:
        op.create_table('template_version_page',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('template_version_id', sa.Integer(), nullable=False),
            sa.Column('filename', sa.String(200), nullable=False),
            sa.Column('content', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['template_version_id'], ['template_version.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('template_version_id', 'filename'),
        )

    template_public_id = {row[0]: row[1] for row in
                           conn.execute(sa.text("SELECT id, public_id FROM template")).fetchall()}

    for template_id, public_id in template_public_id.items():
        current_dir = os.path.join(_root_dir(), public_id, 'current')
        if not os.path.isdir(current_dir):
            continue
        for filename in sorted(os.listdir(current_dir)):
            with open(os.path.join(current_dir, filename), 'r', encoding='utf-8') as f:
                content = f.read()
            conn.execute(sa.text(
                "INSERT INTO template_page (template_id, filename, content) VALUES (:tid, :fn, :ct)"
            ), {'tid': template_id, 'fn': filename, 'ct': content})

    versions = conn.execute(
        sa.text("SELECT id, template_id, version_number FROM template_version")
    ).fetchall()
    for version_id, template_id, version_number in versions:
        public_id = template_public_id.get(template_id)
        if not public_id:
            continue
        version_dir = os.path.join(_root_dir(), public_id, 'versions', str(version_number))
        if not os.path.isdir(version_dir):
            continue
        for filename in sorted(os.listdir(version_dir)):
            with open(os.path.join(version_dir, filename), 'r', encoding='utf-8') as f:
                content = f.read()
            conn.execute(sa.text(
                "INSERT INTO template_version_page (template_version_id, filename, content) "
                "VALUES (:vid, :fn, :ct)"
            ), {'vid': version_id, 'fn': filename, 'ct': content})
