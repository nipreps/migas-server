#!/usr/bin/env python3
"""Exercise the migas-py public API surface against a live migas-server.

Deliberately does not import or run anything from migas-py's own test suite —
those files move around and change layout release to release (setup.cfg vs
pyproject, `migas/tests/` vs `tests/`, hardcoded endpoints). Testing the
public API surface directly is what actually matters for compatibility, and
it's stable across 0.3.0+.

The client's `endpoint` contract changed mid-migration: pre-REST releases
(<=0.4.x) want the full GraphQL URL (`.../graphql`); REST-era releases want
the bare server base URL and append paths themselves. Rather than hardcode
that split by version, this script just tries both and keeps whichever one
the installed client actually accepts.

Usage:
    python check_client_compat.py --server-url http://localhost:8081 [--project nipreps/migas-py]

Exits non-zero (with an explanatory message) on any incompatibility.
"""

import argparse
import inspect
import sys
import time

import migas


def call(fn, *args, **kwargs):
    """Call fn, passing wait=True if it supports it (forces a synchronous response).

    The client swallows its own errors, so anything that isn't a dict becomes {}.
    """
    if 'wait' in inspect.signature(fn).parameters:
        kwargs['wait'] = True
    res = fn(*args, **kwargs)
    return res if isinstance(res, dict) else {}


def get_hits(project):
    return call(migas.get_usage, project, start='2000-01-01').get('hits', 0)


def find_send_fn():
    return getattr(migas, 'add_breadcrumb', None) or getattr(migas, 'add_project', None)


def negotiate_endpoint(base_url, project, client_version):
    """Try both endpoint conventions; return (endpoint, send_fn, response) for the one that works."""
    send = find_send_fn()
    if send is None:
        return None, None, None

    # The bare-base candidate needs a trailing slash: some client versions
    # build the request path via `os.path.join(urlparse(url).path, ...)`,
    # which drops the leading "/" on the joined path when the URL has no
    # path component at all (e.g. "http://host:port" with nothing after).
    for candidate in (f'{base_url.rstrip("/")}/graphql', f'{base_url.rstrip("/")}/'):
        migas.setup(endpoint=candidate)
        try:
            res = call(send, project, client_version)
        except Exception as exc:  # noqa: BLE001 - any client-side failure means "try the other convention"
            print(f'   ({candidate} -> {exc!r})')
            continue
        if res.get('success') is True:
            return candidate, send, res
        print(f'   ({candidate} -> {res})')

    return None, send, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--server-url', required=True, help='Base URL of the migas-server, no trailing path'
    )
    parser.add_argument('--project', default='nipreps/migas-py', help='Registered project to ping')
    args = parser.parse_args()

    client_version = getattr(migas, '__version__', '0.0.0-compat-check')
    print(f'migas-py {client_version} -> {args.server_url}')

    endpoint, send, res = negotiate_endpoint(args.server_url, args.project, client_version)
    if endpoint is None:
        print(
            f'FAIL: no endpoint convention worked for {send.__name__ if send else "<no send fn>"}()'
        )
        return 1
    latest = res.get('latest') or res.get('latest_version')
    print(f'OK   {send.__name__}() via {endpoint} -> success, latest={latest}')

    # The DB may hold crumbs from earlier runs, so check this send is counted.
    before = get_hits(args.project)
    call(send, args.project, client_version)
    # Ingestion may land a beat after the response; retry briefly.
    for _ in range(5):
        usage = call(migas.get_usage, args.project, start='2000-01-01')
        if usage.get('hits', 0) > before:
            break
        time.sleep(1)

    if usage.get('success') is not True:
        print(f'FAIL: get_usage() did not report success: {usage}')
        return 1
    if usage.get('hits', 0) <= before:
        print(f'FAIL: breadcrumb was not ingested (hits stayed at {before}): {usage}')
        return 1
    print(f'OK   get_usage() -> success, hits {before} -> {usage["hits"]}')

    if hasattr(migas, 'check_project'):
        chk = call(migas.check_project, args.project, client_version)
        if chk.get('success') is not True:
            print(f'FAIL: check_project() did not report success: {chk}')
            return 1
        print(f'OK   check_project() -> success, latest={chk.get("latest")}')

    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
