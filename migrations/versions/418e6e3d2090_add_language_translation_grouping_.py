"""Add language, translation grouping, observation and references to Vulnerability

Revision ID: 418e6e3d2090
Revises: a2f5d8e7c164
Create Date: 2026-08-20 14:40:56.270856

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '418e6e3d2090'
down_revision = 'a2f5d8e7c164'
branch_labels = None
depends_on = None


def upgrade():
    # Existing vulnerabilities predate per-language rows and have no locale/translation
    # pairing; per explicit product decision they are wiped rather than backfilled, and
    # repopulated afterward via the new PwnDoc-NG import feature. Deleting before adding
    # the NOT NULL `language` column also sidesteps SQLite's batch-recreate needing a
    # default for pre-existing rows.
    op.execute('DELETE FROM vulnerability')

    with op.batch_alter_table('vulnerability', schema=None) as batch_op:
        batch_op.add_column(sa.Column('observation', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('references', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('language', sa.String(length=5), nullable=False, server_default='EN'))
        batch_op.add_column(sa.Column('translation_group_id', sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f('ix_vulnerability_translation_group_id'), ['translation_group_id'], unique=False)


def downgrade():
    with op.batch_alter_table('vulnerability', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_vulnerability_translation_group_id'))
        batch_op.drop_column('translation_group_id')
        batch_op.drop_column('language')
        batch_op.drop_column('references')
        batch_op.drop_column('observation')
