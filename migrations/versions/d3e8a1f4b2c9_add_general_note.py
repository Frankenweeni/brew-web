"""add general_note table

Revision ID: d3e8a1f4b2c9
Revises: c7a2e5b81d4f
Create Date: 2026-10-03 13:15:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'd3e8a1f4b2c9'
down_revision = 'c7a2e5b81d4f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'general_note',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('general_note')
