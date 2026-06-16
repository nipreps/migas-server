#!/usr/bin/env python
"""Bootstrap (or rotate) the master admin token for a self-hosted migas-server.

Master tokens cannot be created or revoked through the API, so a fresh
Alembic-initialized database has no admin credential. This script generates a
strong token, stores its hash, and prints the raw value once.

Run it with the project's environment (the same DATABASE_* / DATABASE_URL
variables the server uses), e.g.:

    uv run python scripts/bootstrap_admin_token.py
    MIGAS_ENV_FILE=/etc/migas/migas.env uv run python scripts/bootstrap_admin_token.py

By default it refuses to run if a master token already exists. Pass --rotate to
replace the existing token (the old one stops working immediately).
"""

import argparse
import asyncio
import sys
from secrets import token_urlsafe

from sqlalchemy import select

from migas.server.connections import gen_session
from migas.server.database import hash_token
from migas.server.models import Authentication, Projects

MASTER = 'master'


async def bootstrap(desc: str, rotate: bool) -> str:
    raw_token = f'm_{token_urlsafe(32)}'
    hashed = hash_token(raw_token)

    async with gen_session() as session:
        if await session.get(Projects, MASTER) is None:
            session.add(Projects(project=MASTER))

        existing = (
            await session.scalars(select(Authentication).where(Authentication.project == MASTER))
        ).first()

        if existing is not None:
            if not rotate:
                raise SystemExit(
                    'A master token already exists. Re-run with --rotate to replace it.'
                )
            existing.token = hashed
            existing.description = desc
        else:
            session.add(Authentication(project=MASTER, token=hashed, description=desc))

    return raw_token


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        '--rotate',
        '--force',
        action='store_true',
        dest='rotate',
        help='Replace an existing master token instead of failing.',
    )
    parser.add_argument(
        '--desc',
        default='bootstrap admin token',
        help="Description stored alongside the token (default: 'bootstrap admin token').",
    )
    args = parser.parse_args(argv)

    raw_token = asyncio.run(bootstrap(args.desc, args.rotate))

    print('Master token created. Save it now — it cannot be recovered:\n')
    print(f'    {raw_token}\n')
    print('Use it as a bearer token:  Authorization: Bearer <token>')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
