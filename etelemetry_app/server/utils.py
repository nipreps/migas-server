"""Utility functions"""
import json
from datetime import datetime, timezone

# import aiofiles

# from . import CACHEDIR, logger

DATETIME_FMT = "%Y-%m-%dT%H:%M:%SZ"


def str_to_dt(timestamp) -> datetime:
    """Helper method to convert between str / datetime objects"""
    return datetime.strptime(timestamp, DATETIME_FMT).replace(tzinfo=timezone.utc)


def dt_to_str(dt) -> str:
    return dt.strftime(DATETIME_FMT)


def now() -> str | datetime:
    """Return current datetime timestamp. ISO-8601 string"""
    return datetime.now(timezone.utc).replace(microsecond=0)  # ms seems excessive


def diff_in_seconds(t1, t2) -> int:
    """
    Calculate the absolute difference between two datetime objects
    Parameters
    ----------
    t1, t2 : str
    """
    return abs((t1 - t2).total_seconds())


# async def query_project_cache(owner, repo, stale_time=21600):
#     """
#     Search for project cache - if found and valid, return it.
#     :param project: Github project in the form of "owner/repo"
#     :param stale_time: limit until cached results are stale (secs)
#     """
#     cache = CACHEDIR / "{}--{}.json".format(owner, repo)
#     if not cache.exists():
#         return None, "no cache"

#     async with aiofiles.open(str(cache)) as fp:
#         project_info = json.loads(await fp.read())

#     lastmod = project_info.get("last_update")
#     if (
#         lastmod is None
#         or await utc_timediff(lastmod, await get_current_time()) > stale_time
#     ):
#         return project_info, "stale"
#     logger.info(f"Reusing {owner}/{repo} cached version.")
#     return project_info, "cached"


# async def write_project_cache(owner, repo, project_info, update=True):
#     """
#     Write project information to cached file
#     """
#     cache = CACHEDIR / "{}--{}.json".format(owner, repo)
#     if update:
#         project_info["last_update"] = await get_current_time()
#     async with aiofiles.open(str(cache), "w") as fp:
#         await fp.write(json.dumps(project_info))
