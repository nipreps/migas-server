import pytest
from graphql import parse

from ..graphql import _extract_field, _extract_from_ast
from .conftest import TEST_PROJECT, queries


@pytest.mark.parametrize(
    'variables,field,nested_key,expected',
    [
        ({}, 'project', None, None),
        ({'project': TEST_PROJECT}, 'project', None, TEST_PROJECT),
        (
            {'p': {'project': TEST_PROJECT, 'project_version': '1.0.0'}},
            'project',
            None,
            TEST_PROJECT,
        ),
        ({'project': TEST_PROJECT, 'proc': {'status': 'C'}}, 'status', 'proc', 'C'),
        ({'p': {'project': TEST_PROJECT}}, 'status', 'proc', None),
    ],
)
def test_extract_field(variables, field, nested_key, expected):
    assert _extract_field(variables, field, nested_key) == expected


@pytest.mark.parametrize(
    'query,field,nested_key,expected',
    [
        (queries['add_project'], 'project', None, TEST_PROJECT),
        (queries['add_project'], 'project_version', None, '0.5.0'),
        (queries['add_project'], 'status', 'proc', None),
        (queries['add_breadcrumb'], 'project', None, TEST_PROJECT),
        (queries['add_breadcrumb'], 'status', 'proc', 'C'),
        (queries['get_usage'], 'project', None, TEST_PROJECT),
        (queries['get_projects'], 'project', None, None),
    ],
)
def test_extract_from_ast(query, field, nested_key, expected):
    document = parse(query)
    assert _extract_from_ast(document, field, nested_key) == expected


def test_extract_from_ast_empty():
    assert _extract_from_ast(None, 'project') is None
