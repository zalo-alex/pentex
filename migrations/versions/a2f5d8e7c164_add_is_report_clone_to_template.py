"""add is_report_clone to template

Revision ID: a2f5d8e7c164
Revises: f2b6d3a91c58
Create Date: 2026-08-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'a2f5d8e7c164'
down_revision = 'f2b6d3a91c58'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('template', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_report_clone', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('template', schema=None) as batch_op:
        batch_op.drop_column('is_report_clone')
