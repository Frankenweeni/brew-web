"""Add priming sugar fields to batch

Revision ID: b6f1d4a90c3e
Revises: eaf3a864a154
Create Date: 2026-09-25 16:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b6f1d4a90c3e'
down_revision = 'eaf3a864a154'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'batch',
        sa.Column(
            'priming_sugar_amount',
            sa.Float(),
            nullable=True,
            comment='Priming/carbonation sugar added before bottling, in grams',
        ),
    )
    op.add_column(
        'batch',
        sa.Column('priming_sugar_type', sa.String(length=20), nullable=True),
    )


def downgrade():
    op.drop_column('batch', 'priming_sugar_type')
    op.drop_column('batch', 'priming_sugar_amount')
