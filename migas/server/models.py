from sqlalchemy import Column, ForeignKey, Index, MetaData, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.types import BOOLEAN, INTEGER, TIMESTAMP, String, CHAR, DOUBLE_PRECISION

from .connections import AsyncSession

SCHEMA = 'migas'

Base = declarative_base(metadata=MetaData(schema=SCHEMA))


class Projects(Base):
    __tablename__ = 'projects'

    project = Column(String(140), primary_key=True)


class User(Base):
    __tablename__ = 'users'
    __mapper_args__ = {'eager_defaults': True}

    idx = Column(INTEGER, primary_key=True)
    user_id = Column(UUID, unique=True, nullable=False)
    user_type = Column(String(length=32), nullable=False, server_default='general')
    platform = Column(String(length=64), server_default='unknown')
    container = Column(String(length=32), nullable=False, server_default='unknown')
    geoloc_idx = Column(INTEGER)


class Crumb(Base):
    __tablename__ = 'crumbs'
    __mapper_args__ = {'eager_defaults': True}
    __table_args__ = (
        Index('ix_crumbs_project', 'project'),
        Index('ix_crumbs_project_timestamp', 'project', 'timestamp'),
    )

    idx = Column(INTEGER, primary_key=True)
    project = Column(String(140), ForeignKey(f'{SCHEMA}.projects.project'), nullable=False)
    version = Column(String(length=48), nullable=False)
    language = Column(String(length=32), nullable=False)
    language_version = Column(String(length=48), nullable=False)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    session_id = Column(UUID)
    user_id = Column(UUID, ForeignKey(f'{SCHEMA}.users.user_id'), nullable=True)
    status = Column(ENUM('R', 'C', 'F', 'S', name='status'), nullable=False, server_default='R')
    status_desc = Column(String)
    error_type = Column(String)
    error_desc = Column(String)
    is_ci = Column(BOOLEAN, nullable=False)


projects = Projects.__table__


class Authentication(Base):
    __tablename__ = 'auth'
    idx = Column(INTEGER, primary_key=True)
    project = Column(String(length=140), ForeignKey(f'{SCHEMA}.projects.project'), nullable=False)
    token = Column(String, unique=True, nullable=False, index=True)
    description = Column(String)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    last_used = Column(TIMESTAMP(timezone=True), nullable=True)


class GeoLoc(Base):
    __tablename__ = 'geoloc'
    __table_args__ = (
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


async def init_db(session: AsyncSession | None = None) -> None:
    """
    Initialize the database.

    This method ensure the following are created (if not already existing):
    1) migas schema
    2) core tables (projects, users, crumbs, geoloc, auth)
    """
    from sqlalchemy.schema import CreateSchema
    from .connections import get_db_engine

    engine = await get_db_engine()
    # 1) Ensure schema exists and is committed
    async with engine.begin() as conn:
        await conn.execute(CreateSchema(SCHEMA, if_not_exists=True))

    # 2) Create all tables currently defined in metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
