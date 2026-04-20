import pytest
from datetime import datetime, timezone
from migas.server.database import get_viz_data

from .conftest import USER_A, USER_B, SESSION_1, SESSION_2


@pytest.mark.anyio
async def test_viz_bucketing_by_start_date(db):
    """Sessions are bucketed by their start date, even if they end later."""
    project = 'test/viz-start-date'
    await db.register(project)

    day1 = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)

    # Session spans Day 1 -> Day 2; should be bucketed under Day 1.
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
