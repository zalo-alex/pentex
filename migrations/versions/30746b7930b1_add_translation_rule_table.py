"""Add translation_rule table

Revision ID: 30746b7930b1
Revises: a4b927a5c4e5
Create Date: 2026-08-21 11:17:51.222266

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = '30746b7930b1'
down_revision = 'a4b927a5c4e5'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    if 'translation_rule' not in inspector.get_table_names():
        op.create_table('translation_rule',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('public_id', sa.String(36), nullable=False),
            sa.Column('text', sa.Text(), nullable=False),
            sa.Column('source', sa.String(20), nullable=False),
            sa.Column('created_by_id', sa.Integer(), nullable=True),
            sa.Column('created_by_username', sa.String(64), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('public_id'),
        )


def downgrade():
    op.drop_table('translation_rule')
