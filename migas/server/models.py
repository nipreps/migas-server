import typing as ty

from sqlalchemy import Column, MetaData, Table, text
from sqlalchemy.dialects.postgresql import ENUM, UUID, INET
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.types import BOOLEAN, INTEGER, TIMESTAMP, String, CHAR, DOUBLE_PRECISION

from .connections import inject_db_conn

SCHEMA = 'migas'

Base = declarative_base(metadata=MetaData(schema=SCHEMA))


class Projects(Base):
    __tablename__ = "projects"

    project = Column(String(140), primary_key=True)  # 39 owner + "/" + 100 repository


class Project(Base):
    __abstract__ = True
    __mapper_args__ = {"eager_defaults": True}

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
    __mapper_args__ = {"eager_defaults": True}

    idx = Column(INTEGER, primary_key=True)
    user_id = Column(UUID, unique=True)
    user_type = Column(String(length=7), nullable=False)
    platform = Column(String(length=8))
    container = Column(String(length=9), nullable=False)
    asn_idx = Column(INTEGER)
    city_idx = Column(INTEGER)


projects = Projects.__table__


class Authentication(Base):
    __tablename__ = "auth"
    project = Column(String(length=140), primary_key=True)
    token = Column(String)


class LocASN(Base):
    __tablename__ = 'loc_asn'
    idx = Column(INTEGER, primary_key=True)
    start_ip = Column(INET, nullable=False)
    end_ip = Column(INET, nullable=False)
    asn = Column(INTEGER)
    asn_org = Column(String)


class LocCity(Base):
    __tablename__ = 'loc_city'
    idx = Column(INTEGER, primary_key=True)
    start_ip = Column(INET, nullable=False)
    end_ip = Column(INET, nullable=False)
    continent_code = Column(CHAR(2))
    country_code = Column(CHAR(2))
    state_province_name = Column(String)
    city_name = Column(String)
    lat = Column(DOUBLE_PRECISION)
    lon = Column(DOUBLE_PRECISION)



async def get_project_tables(project: str, create: bool = False) -> tuple[Table, Table]:
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
            ProjectModel = type(
                project_class_name,
                (Project,),
                {
                    '__tablename__': project_tablename,
                },
            )
            UsersModel = type(
                users_class_name,
                (ProjectUsers,),
                {
                    '__tablename__': users_tablename,
                },
            )
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
        await create_tables(tables_to_create)

    return project_table, users_table


@inject_db_conn
async def create_tables(tables: list, conn: AsyncConnection) -> None:
    def _create_tables(conn) -> None:
        return Base.metadata.create_all(conn, tables=tables)
    await conn.run_sync(_create_tables)


@inject_db_conn
async def populate_base(conn: AsyncConnection) -> None:
    """Populate declarative class definitions with dynamically created tables."""

    def _has_master_table(conn) -> bool:
        from sqlalchemy import inspect

        return inspect(conn).has_table('projects', schema=SCHEMA)

    if await conn.run_sync(_has_master_table):
        from .database import query_projects

        for project in await query_projects():
            await get_project_tables(project)


@inject_db_conn
async def init_db(conn: AsyncConnection) -> None:
    """
    Initialize the database.

    This method ensure the following are created (if not already existing):
    1) migas schema
    2) project tables
    3) If projects table exists, ensure all tracked projects have Project/ProjectUsers tables.
    """
    from sqlalchemy.schema import CreateSchema
    await conn.execute(CreateSchema('migas', if_not_exists=True))

    # if project is already being monitored, create it
    await populate_base(conn=conn)
    # create all tables
    await conn.run_sync(Base.metadata.create_all)


@inject_db_conn
async def copy_db_from_stream(
    file_bytes: bytes,
    db: ty.Literal['asn', 'city'],
    conn: AsyncConnection,
):
    """
    Write bytes to a table.
    """
    import io

    match db:
        case 'asn':
            table = LocASN
        case 'city':
            table = LocCity
        case _:
            return

    tablename = table.__tablename__
    columns = [c.name for c in table.__table__.columns if c.name != 'idx']
    raw_conn = await conn.get_raw_connection()

    with io.BytesIO(file_bytes) as stream:
        try:
            # asyncpg-specific method
            await raw_conn.driver_connection.copy_to_table(
                table_name=tablename,
                source=stream,
                columns=columns,
                schema_name=SCHEMA,
                format='csv',
                header=False,
            )
        except Exception as e:
            print(f'Error when copying to {db}: {e}')
