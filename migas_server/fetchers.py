import os

import aiohttp

from migas_server.connections import get_redis_connection, get_requests_session

IPSTACK_API_URL = "http://api.ipstack.com/{ip}?access_key={ipstack_secret}"
GITHUB_RELEASE_URL = "https://api.github.com/repos/{project}/releases/latest"
GITHUB_TAG_URL = "https://api.github.com/repos/{project}/tags"
GITHUB_ET_FILE_URL = "https://raw.githubusercontent.com/{project}/{version}/.migas.json"


async def fetch_response(
    url: str, *, params: dict | None = None, content_type: str = "application/json"
):
    session = await get_requests_session()
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


async def fetch_ipstack_data(ip: str) -> dict:
    status, res = await fetch_response(
        IPSTACK_API_URL.format(ip=ip, ipstack_secret=os.getenv("IPSTACK_API_KEY"))
    )
    match status:
        case 200:
            # verify it is valid
            return res
        case _:
            print("IPSTACK: Something went wrong.")
            return {}
