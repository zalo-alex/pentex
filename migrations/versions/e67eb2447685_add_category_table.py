"""add category table

Revision ID: e67eb2447685
Revises: 734afc8e0e8a
Create Date: 2026-03-15 17:16:00.271338

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = 'e67eb2447685'
down_revision = '734afc8e0e8a'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing = inspector.get_table_names()

    if 'category' not in existing:
        op.create_table('category',
            sa.Column('id',   sa.Integer(),     nullable=False),
            sa.Column('name', sa.String(100),   nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name'),
        )

    # Seed default categories (INSERT OR IGNORE is safe to run multiple times)
    for name in ['Web', 'Mobile', 'Infrastructure', 'API', 'Network']:
        conn.execute(sa.text("INSERT OR IGNORE INTO category (name) VALUES (:n)"), {'n': name})

    with op.batch_alter_table('report', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category_id', sa.Integer(), nullable=True))

    with op.batch_alter_table('vulnerability', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category_id', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('vulnerability', schema=None) as batch_op:
        batch_op.drop_column('category_id')

    with op.batch_alter_table('report', schema=None) as batch_op:
        batch_op.drop_column('category_id')

    op.drop_table('category')
