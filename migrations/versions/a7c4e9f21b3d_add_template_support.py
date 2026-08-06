"""add template support (multiple template bundles, linked to category/report)

Revision ID: a7c4e9f21b3d
Revises: f1a2b3c4d5e6
Create Date: 2026-07-21 00:00:00.000000

"""
import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = 'a7c4e9f21b3d'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None

PAGES_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'pages'))


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing = inspector.get_table_names()

    if 'template' not in existing:
        op.create_table('template',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name'),
        )

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

    with op.batch_alter_table('category', schema=None) as batch_op:
        batch_op.add_column(sa.Column('template_id', sa.Integer(), nullable=True))

    with op.batch_alter_table('report', schema=None) as batch_op:
        batch_op.add_column(sa.Column('template_id', sa.Integer(), nullable=True))

    # Seed a "Default" template bundle from the current static/pages/*.hbs + styles.css
    # files, and point every existing category/report at it, so nothing currently in
    # the DB changes behavior after this migration.
    result = conn.execute(sa.text(
        "INSERT INTO template (name, is_default, created_at) VALUES ('Default', 1, CURRENT_TIMESTAMP)"
    ))
    default_id = result.lastrowid
    if not default_id:
        default_id = conn.execute(sa.text("SELECT id FROM template WHERE name = 'Default'")).scalar()

    if os.path.isdir(PAGES_DIR):
        for filename in sorted(os.listdir(PAGES_DIR)):
            filepath = os.path.join(PAGES_DIR, filename)
            if os.path.isdir(filepath):
                continue
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            conn.execute(sa.text(
                "INSERT INTO template_page (template_id, filename, content) VALUES (:tid, :fn, :ct)"
            ), {'tid': default_id, 'fn': filename, 'ct': content})

    conn.execute(sa.text("UPDATE category SET template_id = :tid WHERE template_id IS NULL"), {'tid': default_id})
    conn.execute(sa.text("UPDATE report SET template_id = :tid WHERE template_id IS NULL"), {'tid': default_id})


def downgrade():
    with op.batch_alter_table('report', schema=None) as batch_op:
        batch_op.drop_column('template_id')

    with op.batch_alter_table('category', schema=None) as batch_op:
        batch_op.drop_column('template_id')

    op.drop_table('template_page')
    op.drop_table('template')
