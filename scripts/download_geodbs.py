# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "aiohttp",
#     "tqdm",
# ]
# ///

import argparse
import asyncio
import gzip
import os
import sys
from pathlib import Path

import aiohttp
from tqdm import tqdm


ASN_URL = 'https://osf.io/download/4z3se'
CITY_URL = 'https://osf.io/download/pfhde'


async def download_db(
    session: aiohttp.ClientSession, url: str, db_name: str, out_dir: Path
) -> None:
    out_file = out_dir / f'{db_name}.mmdb'
    if out_file.exists() and out_file.stat().st_size > 0:
        print(f'File {out_file} already exists, skipping download.')
        return

    print(f'Downloading {db_name} database from {url}...')
    temp_gz = out_file.with_suffix('.mmdb.gz')

    try:
        async with session.get(url, allow_redirects=True) as response:
            if response.status != 200:
                print(f'Error: Received status {response.status} from {url}')
                sys.exit(1)

            total = int(response.headers.get('Content-Length', 0))

            with (
                open(temp_gz, 'wb') as f,
                tqdm(
                    total=total, unit_scale=True, unit_divisor=1024, unit='B', desc=db_name
                ) as progress,
            ):
                async for chunk in response.content.iter_chunked(1024 * 64):
                    f.write(chunk)
                    progress.update(len(chunk))

    except Exception as e:
        print(f'Failed to download {db_name} database: {e}')
        if temp_gz.exists():
            temp_gz.unlink()
        sys.exit(1)

    print(f'Decompressing {db_name}...')
    try:
        compressed_data = temp_gz.read_bytes()
        decompressed_data = gzip.decompress(compressed_data)
        out_file.write_bytes(decompressed_data)
        print(f'Successfully saved {out_file} ({len(decompressed_data)} bytes).')
        temp_gz.unlink()  # Cleanup
    except Exception as e:
        print(f'Failed to extract and save {db_name} database: {e}')
        if temp_gz.exists():
            temp_gz.unlink()
        sys.exit(1)


async def async_main():
    parser = argparse.ArgumentParser(
        description='Download geolocation databases for migas-server.'
    )
    parser.add_argument(
        'out_dir',
        nargs='?',
        default='geodb',
        help='Directory to save the MMDB files (default: geodb)',
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Defaults from migas.server.constants
    asn_url = os.getenv('MIGAS_GEOLOC_ASN_URL', ASN_URL)
    city_url = os.getenv('MIGAS_GEOLOC_CITY_URL', CITY_URL)

    async with aiohttp.ClientSession() as session:
        await download_db(session, asn_url, 'asn', out_dir)
        await download_db(session, city_url, 'city', out_dir)


if __name__ == '__main__':
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        sys.exit(1)
