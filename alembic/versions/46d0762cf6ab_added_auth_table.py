"""Added auth table

Revision ID: 46d0762cf6ab
Revises: 93c95bbf67a3
Create Date: 2023-03-02 16:05:15.887855

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '46d0762cf6ab'
down_revision = '93c95bbf67a3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'auth',
        sa.Column('project', sa.String(140), primary_key=True),
        sa.Column('token', sa.String),
        schema='migas',
    )


def downgrade() -> None:
    op.drop_table('auth', schema='migas')
