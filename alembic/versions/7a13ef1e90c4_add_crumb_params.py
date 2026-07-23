"""Add crumb params

Revision ID: 7a13ef1e90c4
Revises: bfb16c778b86
Create Date: 2026-07-10 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '7a13ef1e90c4'
down_revision = 'bfb16c778b86'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'crumbs', sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=True), schema='migas'
    )


def downgrade() -> None:
    op.drop_column('crumbs', 'params', schema='migas')
