"""add template versioning (whole-bundle snapshots)

Revision ID: b3e8f1a92c47
Revises: a7c4e9f21b3d
Create Date: 2026-07-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = 'b3e8f1a92c47'
down_revision = 'a7c4e9f21b3d'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    existing = inspector.get_table_names()

    if 'template_version' not in existing:
        op.create_table('template_version',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('template_id', sa.Integer(), nullable=False),
            sa.Column('version_number', sa.Integer(), nullable=False),
            sa.Column('label', sa.String(200), nullable=True),
            sa.Column('created_by_id', sa.Integer(), nullable=True),
            sa.Column('created_by_username', sa.String(64), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['template_id'], ['template.id']),
            sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('template_id', 'version_number'),
        )

    if 'template_version_page' not in existing:
        op.create_table('template_version_page',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('template_version_id', sa.Integer(), nullable=False),
            sa.Column('filename', sa.String(200), nullable=False),
            sa.Column('content', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['template_version_id'], ['template_version.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('template_version_id', 'filename'),
        )


def downgrade():
    op.drop_table('template_version_page')
    op.drop_table('template_version')
