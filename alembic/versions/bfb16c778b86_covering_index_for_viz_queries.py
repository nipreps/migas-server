"""Covering index for viz queries

Revision ID: bfb16c778b86
Revises: f8cce8b03ed8
Create Date: 2026-04-08 17:54:15.176412

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bfb16c778b86'
down_revision = 'f8cce8b03ed8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop the existing non-covering index
    op.drop_index('ix_crumbs_project_session', table_name='crumbs', schema='migas')

    # 2. Re-create with INCLUDE columns for Index-Only Scans
    op.create_index(
        'ix_crumbs_project_session',
        'crumbs',
        ['project', 'session_id', sa.literal_column('timestamp DESC')],
        unique=False,
        schema='migas',
        postgresql_include=['version', 'status'],
    )


def downgrade() -> None:
    op.drop_index('ix_crumbs_project_session', table_name='crumbs', schema='migas')
    op.create_index(
        'ix_crumbs_project_session',
        'crumbs',
        ['project', 'session_id', sa.literal_column('timestamp DESC')],
        unique=False,
        schema='migas',
    )
