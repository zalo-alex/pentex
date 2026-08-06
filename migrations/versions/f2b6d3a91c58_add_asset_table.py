"""add asset table

Revision ID: f2b6d3a91c58
Revises: e7a4c8b2f915
Create Date: 2026-07-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = 'f2b6d3a91c58'
down_revision = 'e7a4c8b2f915'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    if 'asset' not in inspector.get_table_names():
        op.create_table('asset',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('public_id', sa.String(36), nullable=False),
            sa.Column('filename', sa.String(255), nullable=False),
            sa.Column('content_type', sa.String(127), nullable=True),
            sa.Column('size', sa.Integer(), nullable=False),
            sa.Column('uploaded_by_id', sa.Integer(), nullable=True),
            sa.Column('uploaded_by_username', sa.String(64), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['uploaded_by_id'], ['user.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('public_id'),
        )


def downgrade():
    op.drop_table('asset')
