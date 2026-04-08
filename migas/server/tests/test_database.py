import pytest
from datetime import datetime, timezone, timedelta
from migas.server.database import get_viz_data, insert_crumb, insert_user, add_new_project
from migas.server.connections import gen_session


@pytest.mark.anyio
async def test_get_viz_data_functionality(client):
    """
    Test that get_viz_data handles realistic multi-ping sessions.
    """
    project_name = 'test/viz-data'

    # 1. Register project
    await add_new_project(project_name)

    # 2. Insert test data:
    # Session 1: Start (R) only
    # Session 2: Start (R) -> Complete (C)
    # Session 3: Start (R) -> Fail (F)

    now = datetime.now(timezone.utc)
    one_min_ago = now - timedelta(minutes=1)
    two_min_ago = now - timedelta(minutes=2)

    async with gen_session() as session:
        # Insert users first (FK targets for crumbs.user_id)
        for i in range(1, 4):
            await insert_user(
                user_id=f'00000000-0000-0000-0000-00000000000{i}',
                user_type='hash',
                platform='Linux-5.15.0-88-generic',
                container='unknown',
                geoloc_idx=None,
                session=session,
            )
        # Session 1: Only Start
        await insert_crumb(
            project_name,
            version='1.0.0',
            language='python',
            language_version='3.12',
            timestamp=two_min_ago,
            session_id='00000000-0000-0000-0000-000000000001',
            user_id='00000000-0000-0000-0000-000000000001',
            status='R',
            status_desc=None,
            error_type=None,
            error_desc=None,
            is_ci=False,
            session=session,
        )

        # Session 2: Start -> Complete
        await insert_crumb(
            project_name,
            version='1.0.0',
            language='python',
            language_version='3.12',
            timestamp=two_min_ago,
            session_id='00000000-0000-0000-0000-000000000002',
            user_id='00000000-0000-0000-0000-000000000002',
            status='R',
            status_desc=None,
            error_type=None,
            error_desc=None,
            is_ci=False,
            session=session,
        )
        await insert_crumb(
            project_name,
            version='1.0.0',
            language='python',
            language_version='3.12',
            timestamp=now,
            session_id='00000000-0000-0000-0000-000000000002',
            user_id='00000000-0000-0000-0000-000000000002',
            status='C',
            status_desc=None,
            error_type=None,
            error_desc=None,
            is_ci=False,
            session=session,
        )

        # Session 3: Start -> Fail
        await insert_crumb(
            project_name,
            version='1.0.0',
            language='python',
            language_version='3.12',
            timestamp=two_min_ago,
            session_id='00000000-0000-0000-0000-000000000003',
            user_id='00000000-0000-0000-0000-000000000003',
            status='R',
            status_desc=None,
            error_type=None,
            error_desc=None,
            is_ci=False,
            session=session,
        )
        await insert_crumb(
            project_name,
            version='1.0.0',
            language='python',
            language_version='3.12',
            timestamp=one_min_ago,
            session_id='00000000-0000-0000-0000-000000000003',
            user_id='00000000-0000-0000-0000-000000000003',
            status='F',
            status_desc='Crash',
            error_type='RuntimeError',
            error_desc='Oops',
            is_ci=False,
            session=session,
        )

    # 3. Call get_viz_data
    viz_data = await get_viz_data(project_name)

    # Verify aggregation
    # We expect 3 total distinct sessions.
    # If the logic picks the LATEST status for each session:
    # 1 'R', 1 'C', 1 'F'.
    counts = {d['status']: d['count'] for d in viz_data}
    print(f'Viz data counts: {counts}')

    # These might fail without the ORDER BY fix if Postgres picks the first ping (R)
    assert counts.get('R') == 1, f"Expected 1 'R', got {counts.get('R')}"
    assert counts.get('C') == 1, f"Expected 1 'C', got {counts.get('C')}"
    assert counts.get('F') == 1, f"Expected 1 'F', got {counts.get('F')}"
    assert sum(counts.values()) == 3
