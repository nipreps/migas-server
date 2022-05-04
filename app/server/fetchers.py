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
    # TODO: Implement simple Redis cache
    # Get stale in ~ 2 hours?
    status, res = await fetch_response(GITHUB_RELEASE_URL.format(owner=owner, repo=repo))

    # TODO: Fallback to tag
    # TODO: Write to cache
    if status == 200:
        version = res.get("tag_name") or res.get("name", "Unknown").lstrip("v")

    return {"version": version}
