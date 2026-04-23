"""Tests for GET /api/usage/{project} — weeks param and backward cache extension."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.anyio
async def test_usage_api_weeks_param_limits_response(client: TestClient, db):
    """?weeks=1 returns only rows within the past week; ?weeks=4 returns up to 4 weeks."""
    from datetime import datetime, timezone, timedelta
    from migas.server.tests.conftest import USER_A, SESSION_1, SESSION_2

    project = 'test/api-weeks-limit'
    await db.register(project)
    auth = await db.token(project)

    now = datetime.now(timezone.utc)

    # Crumb inside 1-week window
    await db.crumb(
        project,
        status='C',
        session_id=SESSION_1,
        user_id=USER_A,
        timestamp=now - timedelta(days=3),
    )
    # Crumb outside 1-week window but inside 4-week window
    await db.crumb(
        project,
        status='C',
        session_id=SESSION_2,
        user_id=USER_A,
        timestamp=now - timedelta(days=20),
        ensure_user=False,
    )

    res1 = client.get(f'/api/usage/{project}?weeks=1', headers=auth)
    assert res1.status_code == 200
    dates1 = [r['date'] for r in res1.json()]
    cutoff1 = (now - timedelta(weeks=1)).date().isoformat()
    assert all(d >= cutoff1 for d in dates1), f'weeks=1 returned rows older than {cutoff1}'

    res4 = client.get(f'/api/usage/{project}?weeks=4', headers=auth)
    assert res4.status_code == 200
    dates4 = [r['date'] for r in res4.json()]
    cutoff4 = (now - timedelta(weeks=4)).date().isoformat()
    assert any(d < cutoff1 for d in dates4), 'weeks=4 should include rows older than 1 week'
    assert all(d >= cutoff4 for d in dates4), f'weeks=4 returned rows older than {cutoff4}'


@pytest.mark.anyio
async def test_usage_api_backward_extension_only_queries_gap(client: TestClient, db, monkeypatch):
    """Second request for more weeks only queries the gap, not the already-cached range."""
    from datetime import datetime, timezone, timedelta
    from migas.server.tests.conftest import USER_A, SESSION_1

    project = 'test/api-backward-ext'
    await db.register(project)
    auth = await db.token(project)

    await db.crumb(
        project,
        status='C',
        session_id=SESSION_1,
        user_id=USER_A,
        timestamp=datetime.now(timezone.utc) - timedelta(days=3),
    )

    # Seed the cache with weeks=1
    res1 = client.get(f'/api/usage/{project}?weeks=1', headers=auth)
    assert res1.status_code == 200

    # Intercept get_viz_data calls on the second request (weeks=2)
    from migas.server.api import routes

    calls = []
    original = routes.get_viz_data

    async def tracking_get_viz_data(project_name, start_ts=None, end_ts=None, session=None):
        calls.append({'start_ts': start_ts, 'end_ts': end_ts})
        return await original(project_name, start_ts=start_ts, end_ts=end_ts, session=session)

    monkeypatch.setattr(routes, 'get_viz_data', tracking_get_viz_data)

    res2 = client.get(f'/api/usage/{project}?weeks=2', headers=auth)
    assert res2.status_code == 200

    # The backward extension call must have start_ts approximately 2 weeks ago
    # (not 2000-01-01 — not a full rescan)
    two_weeks_ago = datetime.now(timezone.utc) - timedelta(weeks=2)
    backward_calls = [c for c in calls if c['end_ts'] is not None]
    assert len(backward_calls) >= 1
    earliest_start = min(c['start_ts'] for c in backward_calls)
    assert earliest_start > two_weeks_ago - timedelta(days=1), (
        f'Backward extension scanned too far back: {earliest_start}'
    )


@pytest.mark.anyio
async def test_usage_api_oldest_date_migration(client: TestClient, db):
    """Cache entries without oldest_date are handled gracefully."""
    import json
    import os
    import redis as sync_redis
    from datetime import datetime, timezone, timedelta

    project = 'test/api-migration'
    await db.register(project)
    auth = await db.token(project)

    # Manually write a legacy cache entry (no oldest_date) using sync redis
    # (avoids event-loop mismatch with the async singleton)
    uri = os.getenv('MIGAS_REDIS_URI', 'redis://:@localhost:6379')
    r = sync_redis.from_url(uri, decode_responses=True)
    legacy = {
        'last_date': (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat(),
        'data': [{'date': '2026-04-01', 'version': '1.0.0', 'status': 'C', 'count': 5}],
    }
    r.set(f'migas:viz:hist:{project}', json.dumps(legacy))
    r.close()

    res = client.get(f'/api/usage/{project}?weeks=1', headers=auth)
    assert res.status_code == 200
    # Should not crash; oldest_date derived from min(data[*].date)
    # Legacy row (2026-04-01) is outside the 1-week window — must not appear
    dates = [r['date'] for r in res.json()]
    assert '2026-04-01' not in dates, 'Legacy row outside weeks=1 window should be excluded'


@pytest.mark.anyio
async def test_usage_api_since_returns_only_older_rows(client: TestClient, db):
    """?since=<date> returns only rows strictly older than <date> — the delta
    the client is missing when it already holds data back to <date>."""
    from datetime import datetime, timezone, timedelta
    from migas.server.tests.conftest import USER_A, SESSION_1, SESSION_2

    project = 'test/api-since-delta'
    await db.register(project)
    auth = await db.token(project)

    now = datetime.now(timezone.utc)

    # One crumb the client already has (~3 days old)
    await db.crumb(
        project,
        status='C',
        session_id=SESSION_1,
        user_id=USER_A,
        timestamp=now - timedelta(days=3),
    )
    # One crumb older than the `since` boundary (~20 days)
    await db.crumb(
        project,
        status='C',
        session_id=SESSION_2,
        user_id=USER_A,
        timestamp=now - timedelta(days=20),
        ensure_user=False,
    )

    # Client has data back to 7 days ago; asks for the gap between weeks=4 and there
    since = (now - timedelta(days=7)).date().isoformat()
    res = client.get(f'/api/usage/{project}?weeks=4&since={since}', headers=auth)
    assert res.status_code == 200
    dates = [r['date'] for r in res.json()]
    assert dates, 'delta should include the 20-day-old row'
    assert all(d < since for d in dates), f'delta contained rows >= {since}: {dates}'


@pytest.mark.anyio
async def test_usage_api_cold_cache_no_epoch_scan(client: TestClient, db, monkeypatch):
    """On a cold cache, no DB query should scan from epoch — all start_ts must be bounded."""
    from datetime import datetime, timezone, timedelta
    from migas.server.tests.conftest import USER_A, SESSION_1
    from migas.server.api import routes

    project = 'test/api-cold-cache-bounded'
    await db.register(project)
    auth = await db.token(project)

    await db.crumb(
        project,
        status='C',
        session_id=SESSION_1,
        user_id=USER_A,
        timestamp=datetime.now(timezone.utc) - timedelta(days=3),
    )

    calls = []
    original = routes.get_viz_data

    async def tracking_get_viz_data(project_name, start_ts=None, end_ts=None, session=None):
        calls.append({'start_ts': start_ts, 'end_ts': end_ts})
        return await original(project_name, start_ts=start_ts, end_ts=end_ts, session=session)

    monkeypatch.setattr(routes, 'get_viz_data', tracking_get_viz_data)

    # Cold cache — no prior request, no Redis seed
    res = client.get(f'/api/usage/{project}?weeks=1', headers=auth)
    assert res.status_code == 200

    one_week_ago = datetime.now(timezone.utc) - timedelta(weeks=1)
    for call in calls:
        if call['start_ts'] is not None:
            assert call['start_ts'] > one_week_ago - timedelta(days=2), (
                f'Cold cache triggered scan from {call["start_ts"]} — should be bounded to ~1 week ago'
            )
