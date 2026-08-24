"""Add language to Report

Revision ID: ab32357396c3
Revises: 418e6e3d2090
Create Date: 2026-08-20 15:36:56.170149

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ab32357396c3'
down_revision = '418e6e3d2090'
branch_labels = None
depends_on = None


def upgrade():
    # Existing reports predate per-report language; default them to FR (the app's
    # default authoring language) rather than leaving them unset.
    with op.batch_alter_table('report', schema=None) as batch_op:
        batch_op.add_column(sa.Column('language', sa.String(length=5), nullable=False, server_default='FR'))


def downgrade():
    with op.batch_alter_table('report', schema=None) as batch_op:
        batch_op.drop_column('language')
