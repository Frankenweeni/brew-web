"""add brew monk hydrometer settings

Revision ID: f5a1c3e7b9d2
Revises: e4f9b2c7a1d3
Create Date: 2026-11-08 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'f5a1c3e7b9d2'
down_revision = 'e4f9b2c7a1d3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('app_settings', sa.Column('brewmonk_username', sa.String(length=255), nullable=True))
    op.add_column('app_settings', sa.Column('brewmonk_password', sa.String(length=255), nullable=True))
    op.add_column('app_settings', sa.Column('brewmonk_batch_id', sa.Integer(), nullable=True))
    op.add_column('app_settings', sa.Column('brewmonk_last_sync', sa.DateTime(), nullable=True))
    op.add_column('app_settings', sa.Column('brewmonk_last_status', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('app_settings', 'brewmonk_last_status')
    op.drop_column('app_settings', 'brewmonk_last_sync')
    op.drop_column('app_settings', 'brewmonk_batch_id')
    op.drop_column('app_settings', 'brewmonk_password')
    op.drop_column('app_settings', 'brewmonk_username')
