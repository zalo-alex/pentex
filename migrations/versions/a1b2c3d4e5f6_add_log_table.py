"""add log table

Revision ID: a1b2c3d4e5f6
Revises: e67eb2447685
Create Date: 2026-03-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = 'a1b2c3d4e5f6'
down_revision = 'e67eb2447685'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    if 'log' not in inspector.get_table_names():
        op.create_table('log',
            sa.Column('id',         sa.Integer(),     nullable=False),
            sa.Column('user_id',    sa.Integer(),     nullable=True),
            sa.Column('username',   sa.String(64),    nullable=False),
            sa.Column('action',     sa.String(50),    nullable=False),
            sa.Column('detail',     sa.String(500),   nullable=True),
            sa.Column('ip',         sa.String(45),    nullable=True),
            sa.Column('created_at', sa.DateTime(),    nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
        )


def downgrade():
    op.drop_table('log')
