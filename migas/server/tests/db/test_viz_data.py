"""Database-layer tests for get_viz_data aggregation and bucketing."""

import pytest
from datetime import datetime, timezone, timedelta

from ...database import get_viz_data
from ..conftest import USER_A, USER_B, USER_C, SESSION_1, SESSION_2, SESSION_3


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


@pytest.mark.anyio
async def test_viz_bucketing_by_start_date(db):
    """Sessions are bucketed by their start date, even if they end later."""
    project = 'test/viz-start-date'
    await db.register(project)

    day1 = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)

    await db.crumb(project, status='R', session_id=SESSION_1, user_id=USER_A, timestamp=day1)
    await db.crumb(project, status='C', session_id=SESSION_1, user_id=USER_A, timestamp=day2)

    viz_data = await get_viz_data(project)

    day1_rows = [r for r in viz_data if r['date'] == '2026-04-15']
    assert len(day1_rows) == 1
    assert day1_rows[0]['status'] == 'C'
    assert day1_rows[0]['count'] == 1

    day2_rows = [r for r in viz_data if r['date'] == '2026-04-16']
    assert len(day2_rows) == 0


@pytest.mark.anyio
async def test_get_viz_data_with_cutoff(db):
    """The cutoff parameter filters sessions by start date."""
    project = 'test/viz-cutoff'
    await db.register(project)

    day1 = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)

    await db.crumb(project, status='C', session_id=SESSION_1, user_id=USER_A, timestamp=day1)
    await db.crumb(project, status='C', session_id=SESSION_2, user_id=USER_B, timestamp=day2)

    assert len(await get_viz_data(project)) == 2

    data_cutoff = await get_viz_data(project, start_ts=day2)
    assert len(data_cutoff) == 1
    assert data_cutoff[0]['date'] == '2026-04-16'
