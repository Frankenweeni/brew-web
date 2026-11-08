"""add category to general_note

Revision ID: e4f9b2c7a1d3
Revises: d3e8a1f4b2c9
Create Date: 2026-10-03 14:15:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'e4f9b2c7a1d3'
down_revision = 'd3e8a1f4b2c9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('general_note', sa.Column('category', sa.String(length=20), nullable=True))
    # The single note written before categories existed was a mead note
    op.execute("UPDATE general_note SET category = 'Mead' WHERE category IS NULL")
    op.create_unique_constraint('uq_general_note_category', 'general_note', ['category'])


def downgrade():
    op.drop_constraint('uq_general_note_category', 'general_note', type_='unique')
    op.drop_column('general_note', 'category')
