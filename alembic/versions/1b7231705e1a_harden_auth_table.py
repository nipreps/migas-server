"""harden_auth_table

Revision ID: 1b7231705e1a
Revises: 62e97b5309be
Create Date: 2026-04-14 14:25:34.629145

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1b7231705e1a'
down_revision = '62e97b5309be'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Update auth table
    # Add columns first
    op.add_column('auth', sa.Column('idx', sa.Integer(), autoincrement=True), schema='migas')
    op.add_column('auth', sa.Column('description', sa.String(), nullable=True), schema='migas')
    op.add_column(
        'auth',
        sa.Column(
            'created_at',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        schema='migas',
    )
    op.add_column(
        'auth', sa.Column('last_used', sa.TIMESTAMP(timezone=True), nullable=True), schema='migas'
    )

    # 2. Switch PK
    op.drop_constraint('auth_pkey', 'auth', schema='migas', type_='primary')
    # Use a sequence for the new idx column
    op.execute(sa.text('CREATE SEQUENCE IF NOT EXISTS migas.auth_idx_seq'))
    op.execute(sa.text("UPDATE migas.auth SET idx = nextval('migas.auth_idx_seq')"))
    op.execute(sa.text('ALTER TABLE migas.auth ALTER COLUMN idx SET NOT NULL'))
    op.execute(
        sa.text(
            "ALTER TABLE migas.auth ALTER COLUMN idx SET DEFAULT nextval('migas.auth_idx_seq')"
        )
    )
    op.create_primary_key('auth_pkey', 'auth', ['idx'], schema='migas')
    op.create_index('ix_auth_token', 'auth', ['token'], unique=True, schema='migas')

    # 3. Add 'master' sentinel project
    op.execute("INSERT INTO migas.projects (project) VALUES ('master') ON CONFLICT DO NOTHING")

    # 4. Add FK to auth.project
    op.create_foreign_key(
        'fk_auth_project',
        'auth',
        'projects',
        ['project'],
        ['project'],
        source_schema='migas',
        referent_schema='migas',
    )


def downgrade() -> None:
    op.drop_constraint('fk_auth_project', 'auth', schema='migas', type_='foreignkey')
    op.drop_index('ix_auth_token', table_name='auth', schema='migas')
    op.drop_column('last_used', 'auth', schema='migas')
    op.drop_column('created_at', 'auth', schema='migas')
    op.drop_column('description', 'auth', schema='migas')
    op.drop_column('idx', 'auth', schema='migas')
    # Restore original PK (assuming 'token' was PK)
    op.create_primary_key('auth_pkey', 'auth', ['token'], schema='migas')
    op.execute("DELETE FROM migas.projects WHERE project = 'master'")
