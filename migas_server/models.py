from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import Column, MetaData, Table
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import BOOLEAN, CHAR, FLOAT, INTEGER, TIMESTAMP, String

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


projects = Projects.__table__


async def get_project_tables(
    project: str, create: bool = True
) -> list[Table | None, Table | None]:
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
    if project_table is None and create is True:
        # Dynamically create project and project/users table,
        # and create a relationship between them
        ProjectModel = type(
            project_class_name,
            (Project,),
            {
                '__tablename__': project_tablename,
                'users': relationship(users_class_name, back_populates='project'),
            },
        )
        project_table = tables[project_fullname]
        tables_to_create.append(project_table)

    users_table = tables.get(users_fullname)
    if users_table is None and create is True:
        UsersModel = type(
            users_class_name,
            (ProjectUsers,),
            {
                '__tablename__': users_tablename,
                'project': relationship(project_class_name, back_populates='users'),
            },
        )
        users_table = tables[users_fullname]
        tables_to_create.append(users_table)

    if tables_to_create:
        from .connections import get_db_engine

        engine = await get_db_engine()

        def _create_tables(conn) -> None:
            return Base.metadata.create_all(conn, tables=tables_to_create)

        async with engine.begin() as conn:
            await conn.run_sync(_create_tables)

    return project_table, users_table


async def populate_base(conn: AsyncConnection) -> None:
    """Populate declarative class definitions with dynamically created tables."""

    def _has_master_table(conn) -> bool:
        from sqlalchemy import inspect

        inspector = inspect(conn)
        return inspector.has_table("projects")

    if await conn.run_sync(_has_master_table):
        from migas_server.database import query_projects

        for project in await query_projects():
            await get_project_tables(project)


async def init_db(engine: AsyncEngine) -> None:
    """
    Initialize the database.

    This method ensure the following are created (if not already existing):
    1) migas schema
    2) project tables
    3) If projects table exists, ensure all tracked projects have Project/ProjectUsers tables.
    """
    async with engine.begin() as conn:

        def _has_schema(conn) -> bool:
            from sqlalchemy import inspect

            inspector = inspect(conn)
            return 'migas' in inspector.get_schema_names()

        if not await conn.run_sync(_has_schema):
            # until CreateSchema supports if not exists
            # our best bet is to check schemas and create if not there
            # https://github.com/sqlalchemy/sqlalchemy/issues/7354
            # from sqlalchemy import event
            from sqlalchemy.schema import CreateSchema

            # event.listen(Base.metadata, 'before_create', CreateSchema('migas'))
            await conn.execute(CreateSchema('migas'))

        # if project is already being monitored, create it
        await populate_base(conn)

        # create all tables
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def gen_session() -> AsyncGenerator[AsyncSession, None]:
    """Generate a database session, and close once finished."""
    from .connections import get_db_engine

    # do not expire on commit to allow use of data afterwards
    session = AsyncSession(await get_db_engine(), future=True, expire_on_commit=False)
    async with session.begin():
        try:
            yield session
        finally:
            await session.close()
