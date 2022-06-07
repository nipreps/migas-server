"""Stripped down, minimal import way to communicate with server"""

import argparse
import json
from http.client import HTTPConnection, HTTPSConnection
from urllib.parse import urlparse
from uuid import uuid4


def _parser():
    """Simplify testing"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://0.0.0.0/graphql")
    parser.add_argument("--project", default="nipy/nitransforms")
    parser.add_argument("--version", default="22.0.0")
    parser.add_argument("--user", default=uuid4())
    parser.add_argument("--session", default=uuid4())
    parser.add_argument("--status", choices=("error", "pending", "success"), default="pending")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(pargs=None):
    pargs = _parser().parse_args(pargs)
    owner, repo = pargs.project.split('/')

    mutation = '''
        mutation {
        addProject(
        p: {
        repo: "%s",
        owner: "%s",
        version: "%s",
        language: "python",
        languageVersion: "3.10.4",
        status: %s,
        userId: "%s",
        session: "%s",
        })}''' % (
        repo,
        owner,
        pargs.version,
        pargs.status,
        pargs.user,
        pargs.session,
    )

    purl = urlparse(pargs.url)
    Connection = HTTPSConnection if purl.scheme == 'https' else HTTPConnection
    if pargs.verbose:
        print(mutation)
    body = json.dumps({"query": mutation}).encode("utf-8")

    conn = Connection(purl.netloc)
    headers = {
        'User-Agent': 'etelemetry/0.0.1',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept': '*/*',
        'Connection': 'keep-alive',
        'Content-Length': len(body),
        'Content-Type': 'application/json',
    }

    conn.connect()
    conn.request("POST", purl.path, body, headers)
    response = conn.getresponse()
    data = response.read().decode()
    print(json.loads(data))


if __name__ == "__main__":
    main()
