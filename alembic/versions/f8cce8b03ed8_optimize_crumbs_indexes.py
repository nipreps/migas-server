"""Optimize crumbs indexes

Revision ID: f8cce8b03ed8
Revises: 642a3d0dda0a
Create Date: 2026-04-08 17:24:30.073095

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f8cce8b03ed8'
down_revision = '642a3d0dda0a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop redundant index
    op.drop_index('ix_crumbs_project', table_name='crumbs', schema='migas')

    # 2. Add composite indexes for viz and unique user queries
    op.create_index(
        'ix_crumbs_project_session',
        'crumbs',
        ['project', 'session_id', sa.literal_column('timestamp DESC')],
        schema='migas',
    )
    op.create_index(
        'ix_crumbs_project_user', 'crumbs', ['project', 'user_id'], unique=False, schema='migas'
    )


def downgrade() -> None:
    op.drop_index('ix_crumbs_project_user', table_name='crumbs', schema='migas')
    op.drop_index('ix_crumbs_project_session', table_name='crumbs', schema='migas')
    op.create_index('ix_crumbs_project', 'crumbs', ['project'], unique=False, schema='migas')
