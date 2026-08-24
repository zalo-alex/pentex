"""Add language and translation grouping to Template

Revision ID: a4b927a5c4e5
Revises: ab32357396c3
Create Date: 2026-08-20 16:37:19.991600

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4b927a5c4e5'
down_revision = 'ab32357396c3'
branch_labels = None
depends_on = None


def upgrade():
    # Non-destructive: existing templates simply get language='FR' (this app's
    # default authoring language), no data is touched or removed.
    with op.batch_alter_table('template', schema=None) as batch_op:
        batch_op.add_column(sa.Column('language', sa.String(length=5), nullable=False, server_default='FR'))
        batch_op.add_column(sa.Column('translation_group_id', sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f('ix_template_translation_group_id'), ['translation_group_id'], unique=False)


def downgrade():
    with op.batch_alter_table('template', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_template_translation_group_id'))
        batch_op.drop_column('translation_group_id')
        batch_op.drop_column('language')
