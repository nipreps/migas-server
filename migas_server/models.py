from geoalchemy2 import Geometry  # Geometry("POINT")
from sqlalchemy import Column, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import BOOLEAN, INTEGER, TIMESTAMP, VARCHAR, String

Base = declarative_base()


class Projects(Base):
    __tablename__ = "projects"

    id = Column(INTEGER, primary_key=True)
    projects = Column(VARCHAR(140), unique=True)  # 39 owner + "/" + 100 repository


class Geoloc(Base):
    __tablename__ = "geolocs"
    __mapper_args__ = {"eager_defaults": True}

    idx = Column(INTEGER, autoincrement=True)
    id = Column(String(64), primary_key=True)
    continent = Column(VARCHAR(13), nullable=False)
    country = Column(VARCHAR(56), nullable=False)
    region = Column(VARCHAR(58), nullable=False)
    city = Column(VARCHAR(58), nullable=False)
    postal_code = Column(VARCHAR(10), nullable=False)
    location = Column(Geometry("POINT"), nullable=False)


class Project(Base):
    __abstract__ = True
    __mapper_args__ = {"eager_defaults": True}

    idx = Column(INTEGER, primary_key=True)
    version = Column(VARCHAR(24), nullable=False)
    language = Column(VARCHAR(32), nullable=False)
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


def create_or_get_project_tables(project: str) -> list[Table, Table]:
    """Dynamically create a model from abstract `Project` class."""
    # projects come as <owner>/<repo> strings
    project_tablename = project
    users_tablename = f'{project}/users'
    project_class_name = f'Project_{"_".join(project.split("/"))}'
    users_class_name = f'Users_{"_".join(project.split("/"))}'

    TABLES = Base.metadata.tables

    project_table = TABLES.get(project_tablename)
    if project_table is None:
        # Dynamically create project and project/users table,
        # and create a relationship between them
        Project_Model = type(
            project_class_name,
            (Project,),
            {
                '__tablename__': project_tablename,
                'users': relationship(users_class_name, back_populates='project'),
            },
        )
        project_table = TABLES.get(project_tablename)

    users_table = TABLES.get(users_tablename)
    if users_table is None:
        Users_Model = type(
            users_class_name,
            (ProjectUsers,),
            {
                '__tablename__': users_tablename,
                'project': relationship(project_class_name, back_populates='users'),
            },
        )
        users_table = TABLES.get(users_tablename)
    return project_table, users_table


async def _async_main():
    from migas.connections import get_db_engine

    engine = await get_db_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
