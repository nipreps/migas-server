from sqlalchemy import Column, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import BOOLEAN, FLOAT, INTEGER, TIMESTAMP, VARCHAR, String

Base = declarative_base()


class Projects(Base):
    __tablename__ = "projects"

    project = Column(VARCHAR(140), primary_key=True)  # 39 owner + "/" + 100 repository


class Geolocs(Base):
    __tablename__ = "geolocs"
    __mapper_args__ = {"eager_defaults": True}

    id = Column(String(64), primary_key=True)
    continent = Column(VARCHAR(13), nullable=False)
    country = Column(VARCHAR(56), nullable=False)
    region = Column(VARCHAR(58), nullable=False)
    city = Column(VARCHAR(58), nullable=False)
    postal_code = Column(VARCHAR(10), nullable=False)
    latitude = Column(FLOAT(), nullable=False)
    longitude = Column(FLOAT(), nullable=False)


class Project(Base):
    __abstract__ = True
    __mapper_args__ = {"eager_defaults": True}

    idx = Column(INTEGER, primary_key=True)
    version = Column(VARCHAR(24), nullable=False)
    language = Column(VARCHAR(32), nullable=False)
    language_version = Column(VARCHAR(24), nullable=False)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    session_id = Column(UUID)
    user_id = Column(UUID)  # relationship
    status = Column(VARCHAR(7), nullable=False)
    is_ci = Column(BOOLEAN, nullable=False)


class ProjectUsers(Base):
    __abstract__ = True
    __mapper_args__ = {"eager_defaults": True}

    idx = Column(INTEGER, primary_key=True)
    user_id = Column(UUID, unique=True)
    user_type = Column(VARCHAR(7), nullable=False)
    platform = Column(VARCHAR(8))
    container = Column(VARCHAR(9), nullable=False)


geolocs = Geolocs.__table__
projects = Projects.__table__


def get_project_tables(project: str, create: bool = True) -> list[Table | None, Table | None]:
    """
    Return `Project` and `Users` tables pertaining to input `project`.

    If the models have not yet been created, and `create` is `True`, dynamically creates from
    abstract `Project` and `Users` classes.
    """
    # projects come as <owner>/<repo> strings
    project_tablename = project
    users_tablename = f'{project}/users'
    project_class_name = f'Project_{"_".join(project.split("/"))}'
    users_class_name = f'Users_{"_".join(project.split("/"))}'
    tables = Base.metadata.tables

    project_table = tables.get(project_tablename)
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
        project_table = tables.get(project_tablename)

    users_table = tables.get(users_tablename)
    if users_table is None and create is True:
        UsersModel = type(
            users_class_name,
            (ProjectUsers,),
            {
                '__tablename__': users_tablename,
                'project': relationship(project_class_name, back_populates='users'),
            },
        )
        users_table = tables.get(users_tablename)

    return project_table, users_table


async def db_session() -> AsyncSession:
    """Connection can only be initialized asynchronously"""
    from .connections import get_db_engine

    # do not expire on commit to allow use of data afterwards
    return AsyncSession(await get_db_engine(), future=True, expire_on_commit=False)
