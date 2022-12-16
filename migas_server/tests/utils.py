def form_add_project_query(**params):
    return form_query('mutation', 'add_project', {"p": params})

def form_query(query_type, query_name, **params):
    assert query_type in ('query', 'mutation')
    query = f"{query_type}{{{query_name}("

    query += _expand_parameters(params)
    return query + ")}"

def _expand_parameters(params):
    queries = []
    for name, pargs in params.items():
        if isinstance(pargs, dict):
            queries.append(f"{name}:{{{_expand_parameters(pargs)}}}")
        else:
            queries.append(f"{name}:{pargs}")

    return ','.join(queries)
