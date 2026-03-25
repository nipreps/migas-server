"""refactor_auth_table

Revision ID: 36390660e634
Revises: 46d0762cf6ab
Create Date: 2026-03-25 09:02:45.821844

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '36390660e634'
down_revision = '46d0762cf6ab'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove old primary key on project string
    op.execute('ALTER TABLE migas.auth DROP CONSTRAINT auth_pkey')

    # Add new autoincrementing index, establishing it as the new primary key
    op.execute('ALTER TABLE migas.auth ADD COLUMN idx SERIAL PRIMARY KEY')

    # Add supplemental columns
    op.add_column('auth', sa.Column('description', sa.String(), nullable=True), schema='migas')
    op.add_column(
        'auth',
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        schema='migas',
    )
    op.add_column(
        'auth', sa.Column('last_used', sa.DateTime(timezone=True), nullable=True), schema='migas'
    )

    # Enforce uniqueness perfectly on the token
    op.alter_column('auth', 'token', existing_type=sa.String(), nullable=False, schema='migas')
    op.create_unique_constraint('uq_auth_token', 'auth', ['token'], schema='migas')
    op.create_index(op.f('ix_migas_auth_token'), 'auth', ['token'], unique=True, schema='migas')


def downgrade() -> None:
    # Drop index and unique constraint from token
    op.drop_index(op.f('ix_migas_auth_token'), table_name='auth', schema='migas')
    op.drop_constraint('uq_auth_token', 'auth', schema='migas', type_='unique')
    op.alter_column('auth', 'token', existing_type=sa.String(), nullable=True, schema='migas')

    # Revert primary key constraint
    op.execute('ALTER TABLE migas.auth DROP CONSTRAINT auth_pkey')

    # Drop tracked columns
    op.drop_column('auth', 'last_used', schema='migas')
    op.drop_column('auth', 'created_at', schema='migas')
    op.drop_column('auth', 'description', schema='migas')
    op.drop_column('auth', 'idx', schema='migas')

    # Restore old primary key on project
    op.execute('ALTER TABLE migas.auth ADD PRIMARY KEY (project)')
