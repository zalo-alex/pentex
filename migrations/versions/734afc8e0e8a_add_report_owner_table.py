"""add report_owner table

Revision ID: 734afc8e0e8a
Revises: e3d9e4415bfe
Create Date: 2026-03-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = '734afc8e0e8a'
down_revision = 'e3d9e4415bfe'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    if 'report_owner' not in inspector.get_table_names():
        op.create_table(
            'report_owner',
            sa.Column('report_id', sa.Integer(), sa.ForeignKey('report.id'), primary_key=True),
            sa.Column('user_id',   sa.Integer(), sa.ForeignKey('user.id'),   primary_key=True),
        )

    # Backfill: every existing report gets its original creator as an owner
    conn.execute(sa.text(
        "INSERT OR IGNORE INTO report_owner (report_id, user_id) "
        "SELECT id, user_id FROM report"
    ))


def downgrade():
    op.drop_table('report_owner')
