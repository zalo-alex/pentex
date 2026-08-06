"""add public_id to user, report, vulnerability, template, template_version, category

Revision ID: c9d4e1f83a56
Revises: b3e8f1a92c47
Create Date: 2026-07-21 00:00:00.000000

"""
import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = 'c9d4e1f83a56'
down_revision = 'b3e8f1a92c47'
branch_labels = None
depends_on = None

TABLES = ['user', 'report', 'vulnerability', 'template', 'template_version', 'category']


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    # Step 1: add nullable public_id column to each table (if not already present)
    for table in TABLES:
        existing_cols = {c['name'] for c in inspector.get_columns(table)}
        if 'public_id' not in existing_cols:
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.add_column(sa.Column('public_id', sa.String(36), nullable=True))

    # Step 2: backfill every existing row with a fresh UUID4 (Python-side, since
    # SQLite has no native UUID generation function)
    for table in TABLES:
        rows = conn.execute(sa.text(f'SELECT id FROM "{table}" WHERE public_id IS NULL')).fetchall()
        for row in rows:
            conn.execute(
                sa.text(f'UPDATE "{table}" SET public_id = :pid WHERE id = :id'),
                {'pid': str(uuid.uuid4()), 'id': row.id},
            )

    # Step 3: enforce NOT NULL + UNIQUE via batch mode (required on SQLite)
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column('public_id', existing_type=sa.String(36), nullable=False)
            batch_op.create_unique_constraint(f'uq_{table}_public_id', ['public_id'])


def downgrade():
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(f'uq_{table}_public_id', type_='unique')
            batch_op.drop_column('public_id')
