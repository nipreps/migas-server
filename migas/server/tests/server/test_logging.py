"""LoggingExtension — mocked-unit and live-client integration.

The extension is mounted on the Strawberry schema, so the live test
happens via `/graphql`, but the subject under test is the extension
itself, not GraphQL operations.
"""

import asyncio
import logging
from unittest.mock import MagicMock

from graphql import parse

from ...extensions.logging import LoggingExtension
from ..conftest import TEST_PROJECT, queries


def test_extension_log_format(caplog):
    caplog.set_level(logging.INFO, logger='migas.server')

    mock_ctx = MagicMock()
    mock_ctx.operation_type = MagicMock()
    mock_ctx.operation_type.value = 'query'
    mock_ctx.operation_name = 'GetUsage'
    mock_ctx.variables = {'project': TEST_PROJECT}
    mock_ctx.graphql_document = parse(queries['get_usage'])

    ext = LoggingExtension()
    ext.execution_context = mock_ctx

    async def run_extension():
        async for _ in ext.on_operation():
            pass

    asyncio.run(run_extension())

    log_messages = [rec.message for rec in caplog.records if rec.name == 'migas.server']
    assert any('QUERY GetUsage' in msg for msg in log_messages)
    assert any(f'project={TEST_PROJECT}' in msg for msg in log_messages)


def test_logging_extension(client, caplog):
    caplog.set_level(logging.INFO, logger='migas.server')

    res = client.post('/graphql', json={'query': queries['get_usage']})
    assert res.status_code == 200

    log_messages = [rec.message for rec in caplog.records if rec.name == 'migas.server']
    assert any('QUERY [get_usage]' in msg for msg in log_messages)
    assert any(f'project={TEST_PROJECT}' in msg for msg in log_messages)
