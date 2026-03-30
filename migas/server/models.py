from sqlalchemy import Column, MetaData, Table, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.types import BOOLEAN, INTEGER, TIMESTAMP, String, CHAR, DOUBLE_PRECISION

from .connections import gen_session, AsyncSession

SCHEMA = 'migas'

Base = declarative_base(metadata=MetaData(schema=SCHEMA))


class Projects(Base):
    __tablename__ = 'projects'

    project = Column(String(140), primary_key=True)  # 39 owner + "/" + 100 repository


class Project(Base):
    __abstract__ = True
    __mapper_args__ = {'eager_defaults': True}

    idx = Column(INTEGER, primary_key=True)
    version = Column(String(length=24), nullable=False)
    language = Column(String(length=32), nullable=False)
    language_version = Column(String(length=24), nullable=False)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    session_id = Column(UUID)
    user_id = Column(UUID)  # relationship
    status = Column(ENUM('R', 'C', 'F', 'S', name='status'), nullable=False)
    status_desc = Column(String)
    error_type = Column(String)
    error_desc = Column(String)
    is_ci = Column(BOOLEAN, nullable=False)


class ProjectUsers(Base):
    __abstract__ = True
    __mapper_args__ = {'eager_defaults': True}

    idx = Column(INTEGER, primary_key=True)
    user_id = Column(UUID, unique=True)
    user_type = Column(String(length=7), nullable=False)
    platform = Column(String(length=8))
    container = Column(String(length=9), nullable=False)
    asn_idx = Column(INTEGER)
    city_idx = Column(INTEGER)
    geoloc_idx = Column(INTEGER)


projects = Projects.__table__


class Authentication(Base):
    __tablename__ = 'auth'
    idx = Column(INTEGER, primary_key=True)
    project = Column(String(length=140), nullable=False)
    token = Column(String, unique=True, nullable=False, index=True)
    description = Column(String)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    last_used = Column(TIMESTAMP(timezone=True), nullable=True)


class GeoLoc(Base):
    __tablename__ = 'geoloc'
    table_args = (
        UniqueConstraint(
            'country_code', 'state_province_name', 'city_name', 'lat', 'lon', name='unique_loc_idx'
        ),
    )

    idx = Column(INTEGER, primary_key=True)
    asn = Column(INTEGER)
    asn_org = Column(String)
    continent_code = Column(CHAR(2))
    country_code = Column(CHAR(2))
    state_province_name = Column(String)
    city_name = Column(String)
    lat = Column(DOUBLE_PRECISION)
    lon = Column(DOUBLE_PRECISION)


async def get_project_tables(
    project: str, create: bool = False, session: AsyncSession | None = None
) -> tuple[Table, Table]:
    """
    Return `Project` and `Users` tables pertaining to input `project`.

    If the models have not yet been created, and `create` is `True`, dynamically creates from
    abstract `Project` and `Users` classes.
    """
    # projects come as <owner>/<repo> strings
    project_tablename = project
    project_fullname = f'{SCHEMA}.{project_tablename}'
    users_tablename = f'{project}/users'
    users_fullname = f'{SCHEMA}.{users_tablename}'
    project_class_name = f'Project_{"_".join(project.split("/"))}'
    users_class_name = f'Users_{"_".join(project.split("/"))}'
    tables = Base.metadata.tables
    tables_to_create = []

    project_table = tables.get(project_fullname)
    users_table = tables.get(users_fullname)
    if create:
        if project_table is None and users_table is None:
            # Dynamically create project and project/users table,
            # and create a relationship between them
            type(project_class_name, (Project,), {'__tablename__': project_tablename})
            type(users_class_name, (ProjectUsers,), {'__tablename__': users_tablename})
            # # assign relationships once both are defined
            # ProjectModel.users = relationship(users_class_name, back_populates='project')
            # UsersModel.project = relationship(project_class_name, back_populates='users')

            users_table = tables[users_fullname]
            project_table = tables[project_fullname]
            tables_to_create = [users_table, project_table]
        elif project_table is None or users_table is None:
            # missing complimentary table
            raise RuntimeError(f'Missing required table for {project}')

    if tables_to_create:
        await create_tables(tables_to_create, session=session)

    return project_table, users_table


async def create_tables(tables: list, session: AsyncSession | None = None) -> None:
    async with gen_session(session) as session:
        conn = await session.connection()

        def _create_tables(sync_conn) -> None:
            return Base.metadata.create_all(sync_conn, tables=tables)

        await conn.run_sync(_create_tables)


async def populate_base(session: AsyncSession | None = None) -> None:
    """Populate declarative class definitions with dynamically created tables."""

    async with gen_session(session) as session:
        conn = await session.connection()

        def _has_master_table(sync_conn) -> bool:
            from sqlalchemy import inspect

            return inspect(sync_conn).has_table('projects', schema=SCHEMA)

        if await conn.run_sync(_has_master_table):
            from .database import query_projects

            for project in await query_projects(session=session):
                await get_project_tables(project, session=session)


async def init_db(session: AsyncSession | None = None) -> None:
    """
    Initialize the database.

    This method ensure the following are created (if not already existing):
    1) migas schema
    2) project tables
    3) If projects table exists, ensure all tracked projects have Project/ProjectUsers tables.
    """
    from sqlalchemy.schema import CreateSchema

    async with gen_session(session) as session:
        conn = await session.connection()
        await conn.execute(CreateSchema('migas', if_not_exists=True))

        # if project is already being monitored, create it
        await populate_base(session=session)
        # create all tables
        await conn.run_sync(Base.metadata.create_all)
