import logging
from functools import wraps

import aiohttp

from .connections import get_redis_connection, get_requests_session, ClientSession

logger = logging.getLogger('migas')

GITHUB_RELEASE_URL = 'https://api.github.com/repos/{project}/releases/latest'
GITHUB_TAG_URL = 'https://api.github.com/repos/{project}/tags'
GITHUB_ET_FILE_URL = 'https://raw.githubusercontent.com/{project}/{version}/.migas.json'


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
    content_type: str = 'application/json',
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
                for bad_version in et.get('bad_versions', set()):
                    await cache.sadd(f'{project}/bad_versions', bad_version)

        # write to cache
        await cache.hset(project, 'latest_version', latest_version)
        await cache.expire(project, 21600)  # force fetch every 6 hours

    bad_versions = await cache.smembers(f'{project}/bad_versions') or set()

    return {
        'bad_versions': list(bad_versions),
        'cached': not cache_miss,
        'success': latest_version not in ('unknown', 'forbidden'),
        'version': latest_version.lstrip('v'),
    }


async def geoloc(ip: str, lang: str = 'en') -> dict | None:
    from .connections import get_mmdb_reader

    city, asn = await get_mmdb_reader()
    if not city or not asn:
        return

    info = {}
    cinfo = city.get(ip)
    if not cinfo:
        logger.debug(f'No geolocation info for IP: {ip}')
        return
    info['city'] = cinfo['city']['names'][lang]
    info['continent_code'] = cinfo['continent']['code']
    info['country_code'] = cinfo['country']['iso_code']
    info['lat'] = cinfo['location']['latitude']
    info['lon'] = cinfo['location']['longitude']
    if subdivs := cinfo['subdivisions']:
        info['state_or_province'] = subdivs[0]['names'][lang]

    ainfo = asn.get(ip)
    if not ainfo:
        logger.debug(f'No geolocation info for IP: {ip}')
        return info
    info['asn'] = ainfo['autonomous_system_number']
    info['aso'] = ainfo['autonomous_system_organization']
    return info
