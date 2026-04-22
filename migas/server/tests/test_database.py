import pytest
from datetime import datetime, timezone, timedelta

from migas.server.database import get_viz_data

from .conftest import USER_A, USER_B, USER_C, SESSION_1, SESSION_2, SESSION_3


@pytest.mark.anyio
async def test_get_viz_data_functionality(db):
    """get_viz_data picks the latest status per session within the date bucket.

    Session 1 is Running only, Session 2 Running → Complete, Session 3
    Running → Failed. Expect one row each for R, C, F.
    """
    project = 'test/viz-data'
    await db.register(project)

    now = datetime.now(timezone.utc)
    one_min_ago = now - timedelta(minutes=1)
    two_min_ago = now - timedelta(minutes=2)

    await db.crumb(
        project, status='R', session_id=SESSION_1, user_id=USER_A, timestamp=two_min_ago
    )

    await db.crumb(
        project, status='R', session_id=SESSION_2, user_id=USER_B, timestamp=two_min_ago
    )
    await db.crumb(project, status='C', session_id=SESSION_2, user_id=USER_B, timestamp=now)

    await db.crumb(
        project, status='R', session_id=SESSION_3, user_id=USER_C, timestamp=two_min_ago
    )
    await db.crumb(
        project,
        status='F',
        session_id=SESSION_3,
        user_id=USER_C,
        timestamp=one_min_ago,
        status_desc='Crash',
        error_type='RuntimeError',
        error_desc='Oops',
    )

    counts = {d['status']: d['count'] for d in await get_viz_data(project)}
    assert counts == {'R': 1, 'C': 1, 'F': 1}
