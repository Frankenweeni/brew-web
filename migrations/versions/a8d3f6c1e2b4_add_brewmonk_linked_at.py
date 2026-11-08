"""add brew monk link time

Revision ID: a8d3f6c1e2b4
Revises: f5a1c3e7b9d2
Create Date: 2026-11-08 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'a8d3f6c1e2b4'
down_revision = 'f5a1c3e7b9d2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('app_settings', sa.Column('brewmonk_linked_at', sa.DateTime(), nullable=True))
    # Keep an existing link, counting from now
    op.execute("UPDATE app_settings SET brewmonk_linked_at = now() WHERE brewmonk_batch_id IS NOT NULL")


def downgrade():
    op.drop_column('app_settings', 'brewmonk_linked_at')
