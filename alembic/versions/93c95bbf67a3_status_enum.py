"""status-enum

Revision ID: 93c95bbf67a3
Revises: 6d01a9e7093b
Create Date: 2022-08-26 10:35:56.131795

"""

import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as psg

from alembic import op

# revision identifiers, used by Alembic.
revision = '93c95bbf67a3'
down_revision = '6d01a9e7093b'
branch_labels = None
depends_on = None
schema = 'migas'


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    for project in get_tracked_projects():
        existing_columns = [c['name'] for c in inspector.get_columns(project, schema=schema)]

        if 'status_desc' not in existing_columns:
            # alter status column to use enum over varchar
            status_type = psg.ENUM('R', 'C', 'F', 'S', name='status')
            pt = create_adhoc_project_table(project, status_type)
            op.alter_column(project, 'status', existing_type=status_type, schema=schema)

            op.add_column(project, sa.Column('status_desc', sa.String()), schema=schema)
            if 'error_type' not in existing_columns:
                op.add_column(project, sa.Column('error_type', sa.String()), schema=schema)
            if 'error_desc' not in existing_columns:
                op.add_column(project, sa.Column('error_desc', sa.String()), schema=schema)

            # These updates only make sense if we are converting FROM varchar TO enum
            conn.execute(pt.update().where(pt.c.status == 'success').values(status='C'))
            conn.execute(pt.update().where(pt.c.status == 'pending').values(status='R'))
            conn.execute(pt.update().where(pt.c.status == 'error').values(status='F'))
        # No need for conn.commit() here as Alembic handles transactional DDL


def downgrade() -> None:
    projects = get_tracked_projects()
    for project in projects:
        status_type = psg.VARCHAR(7)
        op.alter_column(project, 'status', type_=status_type, schema=schema)
        op.drop_column(project, 'status_desc', schema=schema)
        op.drop_column(project, 'error_type', schema=schema)
        op.drop_column(project, 'error_desc', schema=schema)


def get_tracked_projects() -> list[str]:
    conn = op.get_bind()
    projects = conn.execute(sa.text('select project from migas.projects')).scalars().fetchall()
    return projects


def create_adhoc_project_table(project, status_type=None) -> sa.sql.expression.TableClause:
    pt = sa.table(
        project,
        sa.column('idx'),
        sa.column('version'),
        sa.column('language'),
        sa.column('language_version'),
        sa.column('timestamp'),
        sa.column('session_id'),
        sa.column('user_id'),
        sa.column('status', status_type),
        sa.column('is_ci'),
        schema='migas',
    )
    return pt
