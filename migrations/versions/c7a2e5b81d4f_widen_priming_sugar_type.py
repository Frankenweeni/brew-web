"""widen batch.priming_sugar_type

Revision ID: c7a2e5b81d4f
Revises: b6f1d4a90c3e
Create Date: 2026-09-28 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c7a2e5b81d4f'
down_revision = 'b6f1d4a90c3e'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('batch', schema=None) as batch_op:
        batch_op.alter_column('priming_sugar_type',
                              existing_type=sa.String(length=20),
                              type_=sa.String(length=50),
                              existing_nullable=True)


def downgrade():
    with op.batch_alter_table('batch', schema=None) as batch_op:
        batch_op.alter_column('priming_sugar_type',
                              existing_type=sa.String(length=50),
                              type_=sa.String(length=20),
                              existing_nullable=True)
