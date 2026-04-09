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

    # 8. Data Migration
    conn = op.get_bind()
    # Discover all dynamic tables from existing projects
    res = conn.execute(sa.text("SELECT project FROM migas.projects WHERE project != 'master'"))
    projects = res.scalars().all()

    # Phase 8a: Migrate ALL users first to satisfy FK constraints for crumbs
    for project in projects:
        users_table = f'{project}/users'
        cols_res = conn.execute(
            sa.text(
                'SELECT column_name FROM information_schema.columns '
                "WHERE table_schema = 'migas' AND table_name = :tbl"
            ),
            {'tbl': users_table},
        )
        source_cols = {r[0] for r in cols_res}

        if 'geoloc_idx' in source_cols:
            op.execute(
                sa.text(f"""
                INSERT INTO migas.users (user_id, user_type, platform, container, geoloc_idx)
                SELECT user_id, user_type, platform, container, geoloc_idx
                FROM migas."{users_table}"
                ON CONFLICT (user_id) DO NOTHING
            """)
            )
        else:
            op.execute(
                sa.text(f"""
                INSERT INTO migas.users (user_id, user_type, platform, container)
                SELECT user_id, user_type, platform, container
                FROM migas."{users_table}"
                ON CONFLICT (user_id) DO NOTHING
            """)
            )

    # Phase 8b: Ghost User Catch-up
    # In some production cases, crumbs exist for users NOT in the /users tables.
    # We create placeholder user records for these orphans to satisfy FKs.
    for project in projects:
        op.execute(
            sa.text(f"""
            INSERT INTO migas.users (user_id, user_type, platform, container)
            SELECT DISTINCT user_id, 'unknown', 'unknown', 'unknown'
            FROM migas."{project}"
            WHERE user_id IS NOT NULL
            ON CONFLICT (user_id) DO NOTHING
        """)
        )

    # Phase 8c: Migrate crumbs after all users (real and ghost) are in place
    for project in projects:
        conn.execute(
            sa.text(f"""
            INSERT INTO migas.crumbs (
                project, version, language, language_version, timestamp,
                session_id, user_id, status, status_desc, error_type, error_desc, is_ci
            )
            SELECT
                :project, version, language, language_version, timestamp,
                session_id, user_id, status, status_desc, error_type, error_desc, is_ci
            FROM migas."{project}"
            WHERE timestamp >= now() - interval '2 years'
        """),
            {'project': project},
        )

    # 6. Drop old tables
    for project in projects:
        op.drop_table(f'{project}/users', schema='migas')
        op.drop_table(project, schema='migas')


def downgrade() -> None:
    # Breaking change, downgrade will drop the consolidated data.
    op.drop_constraint('fk_auth_project', 'auth', schema='migas', type_='foreignkey')
    op.drop_index('ix_crumbs_project_timestamp', table_name='crumbs', schema='migas')
    op.drop_index('ix_crumbs_project', table_name='crumbs', schema='migas')
    op.drop_table('crumbs', schema='migas')
    op.drop_table('users', schema='migas')
    op.execute("DELETE FROM migas.projects WHERE project = 'master'")
