from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import Column, MetaData, Table
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import BOOLEAN, INTEGER, TIMESTAMP, String

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


class Authentication(Base):
    __tablename__ = "auth"
    project = Column(String(length=140), primary_key=True)
    token = Column(String)


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


async def create_tables(tables: list) -> None:
    from .connections import get_db_engine

    engine = await get_db_engine()
    async with engine.begin() as conn:
        def _create_tables(conn) -> None:
            return Base.metadata.create_all(conn, tables=tables)
        await conn.run_sync(_create_tables)


async def populate_base(conn: AsyncConnection) -> None:
    """Populate declarative class definitions with dynamically created tables."""

    def _has_master_table(conn) -> bool:
        from sqlalchemy import inspect

        inspector = inspect(conn)
        return inspector.has_table("projects", schema='migas')

    if await conn.run_sync(_has_master_table):
        from .database import query_projects

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
        from sqlalchemy.schema import CreateSchema
        await conn.execute(CreateSchema('migas', if_not_exists=True))

        # if project is already being monitored, create it
        await populate_base(conn)
        # create all tables
        await conn.run_sync(Base.metadata.create_all)

SessionGen = AsyncGenerator[AsyncSession, None]

@asynccontextmanager
async def gen_session() -> SessionGen:
    """Generate a database session, and close once finished."""
    from .connections import get_db_engine

    # do not expire on commit to allow use of data afterwards
    session = AsyncSession(await get_db_engine(), future=True, expire_on_commit=False)
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        print(f"Transaction failed. Rolling back the session. Error: {e}")
    finally:
        await session.close()
