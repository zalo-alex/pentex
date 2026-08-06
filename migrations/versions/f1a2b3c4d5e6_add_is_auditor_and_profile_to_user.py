"""add is_auditor, full_name, email to user

Revision ID: f1a2b3c4d5e6
Revises: de13f5e3a376
Create Date: 2026-07-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'de13f5e3a376'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_auditor', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('full_name', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('email', sa.String(length=200), nullable=True))


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('email')
        batch_op.drop_column('full_name')
        batch_op.drop_column('is_auditor')
