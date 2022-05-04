import asyncio

import aiohttp

GITHUB_RELEASE_URL = "https://api.github.com/repos/{owner}/{repo}/releases/latest"
GITHUB_TAG_URL = "https://api.github.com/repos/{owner}/{repo}/tags"

Session = aiohttp.ClientSession(headers={'Content-Type': 'application/json'})


async def fetch_response(
    url: str, *, params: dict | None = None, content_type: str = "application/json"
):
    async with Session.get(url, params=params) as response:
        try:
            res = await response.json(content_type=content_type)
        except ValueError:
            res = await response.text()
        status = response.status
    return status, res


async def fetch_project_info(
    owner: str,
    repo: str,
):
    retry = 0
    version = "unknown"
    while retry < 5:
        # TODO: Implement simple Redis cache to avoid excessive GH API calls
        status, res = await fetch_response(GITHUB_RELEASE_URL.format(owner=owner, repo=repo))

        # TODO: Fallback to tag
        # TODO: Write to cache
        match status:
            case 200:
                version = res.get("tag_name") or res.get("name", "Unknown").lstrip("v")
                break
            case _:
                if retry == 5:
                    raise aiohttp.web.HTTPException("Could not fetch version")
                asyncio.sleep(5)
                print(f"Something went wrong while fetching ({status})...retrying")
                retry += 1

    return {"version": version}
