import typing as ty
import os
import gzip
from functools import wraps

import aiohttp

from .connections import get_redis_connection, get_requests_session, ClientSession

GITHUB_RELEASE_URL = "https://api.github.com/repos/{project}/releases/latest"
GITHUB_TAG_URL = "https://api.github.com/repos/{project}/tags"
GITHUB_ET_FILE_URL = "https://raw.githubusercontent.com/{project}/{version}/.migas.json"


def inject_aiohttp_session(func):
    """Decorator that injects the global session to a function."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        session = kwargs.pop('session', None)
        if not session:
            session = await get_requests_session()
        return await func(*args, session=session, **kwargs)
    return wrapper


@inject_aiohttp_session
async def fetch_response(
    url: str,
    *,
    session: ClientSession,
    params: dict | None = None,
    headers: dict | None = None,
    content_type: str = "application/json",
):
    request_headers = headers or {}
    request_headers['Content-Type'] = content_type
    async with session.get(url, params=params) as response:
        try:
            res = await response.json(content_type=content_type)
        except (aiohttp.ContentTypeError, ValueError):
            res = await response.text()
        status = response.status
    return status, res


async def fetch_project_info(project: str) -> dict:
    cache = await get_redis_connection()
    latest_version = await cache.hget(project, 'latest_version') or 'unknown'

    if cache_miss := latest_version == 'unknown':
        rstatus, release = await fetch_response(GITHUB_RELEASE_URL.format(project=project))
        match rstatus:
            case 200:
                latest_version = release.get('tag_name')
            case 403:
                latest_version = 'forbidden'  # avoid excessive queries if repo is private
            case 404:
                # fallback to tag
                tstatus, tag = await fetch_response(GITHUB_TAG_URL.format(project=project))
                match tstatus:
                    case 200:
                        try:
                            latest_version = tag[0].get('name')
                        except IndexError:  # no tags will return empty list
                            pass
                    case _:
                        pass
            case _:
                pass
        if latest_version not in ('unknown', 'forbidden'):
            # query for ET file
            estatus, et = await fetch_response(
                GITHUB_ET_FILE_URL.format(project=project, version=latest_version)
            )
            if estatus == 200:
                for bad_version in et.get("bad_versions", set()):
                    await cache.sadd(f'{project}/bad_versions', bad_version)

        # write to cache
        await cache.hset(project, 'latest_version', latest_version)
        await cache.expire(project, 21600)  # force fetch every 6 hours

    bad_versions = await cache.smembers(f'{project}/bad_versions') or set()

    return {
        "bad_versions": list(bad_versions),
        "cached": not cache_miss,
        "success": latest_version not in ('unknown', 'forbidden'),
        "version": latest_version.lstrip('v'),
    }


@inject_aiohttp_session
async def fetch_gzipped_file(url: str, *, session: ClientSession) -> bytes | None:
    """Get the already processed database file"""
    async with session.get(url, timeout=60) as resp:
        if resp.status != 200:
            return
        content = await resp.read()
    return gzip.decompress(content)


async def download_ingest_csv(url: str, db: ty.Literal['asn', 'city']):
    from .models import copy_db_from_stream

    file_bytes = await fetch_gzipped_file(url)
    if file_bytes:
        await copy_db_from_stream(file_bytes, db)


async def fetch_loc_dbs(app):
    """
    1. Check if location databases are empty
    2. If not, fetch preprocessed location CSVs.
    2. Ingest into Postgres
    """
    if not os.getenv('MIGAS_DOWNLOAD_LOCATION'):
        return False

    from .database import valid_location_dbs
    valid_asn, valid_city = await valid_location_dbs()
    if not valid_asn:
        from .constants import LOC_ASN_URL

        print('Downloading location data (ASN)')
        await download_ingest_csv(LOC_ASN_URL, db='asn')
    else:
        print('Found valid ASN database')

    if not valid_city:
        from .constants import LOC_CITY_URL

        print('Downloading location data (CITY)')
        await download_ingest_csv(LOC_CITY_URL, db='city')
    else:
        print('Found valid CITY database')
