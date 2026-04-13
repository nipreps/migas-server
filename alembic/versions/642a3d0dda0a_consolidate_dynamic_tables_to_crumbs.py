"""Consolidate dynamic tables to crumbs and users

Revision ID: 642a3d0dda0a
Revises: 46d0762cf6ab
Create Date: 2026-04-08 15:32:19.155338

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '642a3d0dda0a'
down_revision = '46d0762cf6ab'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create users table
    op.create_table(
        'users',
        sa.Column('idx', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('user_type', sa.String(length=32), server_default='general', nullable=False),
        sa.Column('platform', sa.String(length=64), server_default='unknown', nullable=True),
        sa.Column('container', sa.String(length=32), server_default='unknown', nullable=False),
        sa.Column('geoloc_idx', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('idx'),
        sa.UniqueConstraint('user_id'),
        schema='migas',
    )

    # 2. Move status enum from public to migas schema
    op.execute(sa.text('ALTER TYPE public.status SET SCHEMA migas'))

    # 3. Create crumbs table
    op.create_table(
        'crumbs',
        sa.Column('idx', sa.Integer(), nullable=False),
        sa.Column('project', sa.String(length=140), nullable=False),
        sa.Column('version', sa.String(length=48), nullable=False),
        sa.Column('language', sa.String(length=32), nullable=False),
        sa.Column('language_version', sa.String(length=48), nullable=False),
        sa.Column(
            'timestamp',
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('session_id', sa.UUID(), nullable=True),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column(
            'status',
            postgresql.ENUM('R', 'C', 'F', 'S', name='status', schema='migas', create_type=False),
            server_default='R',
            nullable=False,
        ),
        sa.Column('status_desc', sa.String(), nullable=True),
        sa.Column('error_type', sa.String(), nullable=True),
        sa.Column('error_desc', sa.String(), nullable=True),
        sa.Column('is_ci', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['project'], ['migas.projects.project']),
        sa.ForeignKeyConstraint(['user_id'], ['migas.users.user_id']),
        sa.PrimaryKeyConstraint('idx'),
        schema='migas',
    )
    op.create_index('ix_crumbs_project', 'crumbs', ['project'], unique=False, schema='migas')
    op.create_index(
        'ix_crumbs_project_timestamp',
        'crumbs',
        ['project', 'timestamp'],
        unique=False,
        schema='migas',
    )

    # 3. Create geoloc table
    op.create_table(
        'geoloc',
        sa.Column('idx', sa.Integer(), nullable=False),
        sa.Column('asn', sa.Integer(), nullable=True),
        sa.Column('asn_org', sa.String(), nullable=True),
        sa.Column('continent_code', sa.CHAR(length=2), nullable=True),
        sa.Column('country_code', sa.CHAR(length=2), nullable=True),
        sa.Column('state_province_name', sa.String(), nullable=True),
        sa.Column('city_name', sa.String(), nullable=True),
        sa.Column('lat', sa.DOUBLE_PRECISION(), nullable=True),
        sa.Column('lon', sa.DOUBLE_PRECISION(), nullable=True),
        sa.PrimaryKeyConstraint('idx'),
        sa.UniqueConstraint(
            'country_code', 'state_province_name', 'city_name', 'lat', 'lon', name='unique_loc_idx'
        ),
        schema='migas',
    )

    # 4. Update auth table
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

    # Switch PK
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

    # 5. Add 'master' sentinel project
    op.execute("INSERT INTO migas.projects (project) VALUES ('master') ON CONFLICT DO NOTHING")

    # 6. Add FK to auth.project
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
    # Breaking change, downgrade will drop the consolidated data.
    op.drop_constraint('fk_auth_project', 'auth', schema='migas', type_='foreignkey')
    op.drop_index('ix_crumbs_project_timestamp', table_name='crumbs', schema='migas')
    op.drop_index('ix_crumbs_project', table_name='crumbs', schema='migas')
    op.drop_table('crumbs', schema='migas')
    op.drop_table('users', schema='migas')
    op.execute("DELETE FROM migas.projects WHERE project = 'master'")
