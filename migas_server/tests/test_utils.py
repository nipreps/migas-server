import pytest

from .utils import form_query


@pytest.mark.parametrize('query_type,query_name,params,expected', [
    ('query', 'test', {}, 'query{test()}'),
    ('mutation', 'test', {"key": "value"}, 'mutation{test(key:value)}'),
    ('mutation', 'testintest', {"object": {"attribute": '"val"'}}, 'mutation{testintest(object:{attribute:"val"})}')
])
def test_form_query(query_type, query_name, params, expected):
    query = form_query(query_type, query_name, **params)
    assert query == expected
