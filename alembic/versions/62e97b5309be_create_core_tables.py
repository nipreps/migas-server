"""create_core_tables

Revision ID: 62e97b5309be
Revises: 46d0762cf6ab
Create Date: 2026-04-14 14:25:32.483612

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '62e97b5309be'
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
    # Note: If this fails because it's already in migas (from a previous dry run), ignore
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

    # 4. Create geoloc table
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


def downgrade() -> None:
    op.drop_table('geoloc', schema='migas')
    op.drop_index('ix_crumbs_project_timestamp', table_name='crumbs', schema='migas')
    op.drop_index('ix_crumbs_project', table_name='crumbs', schema='migas')
    op.drop_table('crumbs', schema='migas')
    op.drop_table('users', schema='migas')
