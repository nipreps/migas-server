import sys


def get_parser():
    from argparse import ArgumentParser

    def _fmt_kv_pairs(value):
        return value.split(":", 1)

    parser = ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0", help="hostname")
    parser.add_argument("--port", default=8000, type=int, help="server port")
    parser.add_argument("--workers", default=1, help="worker processes")
    parser.add_argument("--reload", action="store_true", help="Reload app on change (dev only)")
    parser.add_argument(
        "--proxy-headers",
        action="store_true",
        help="Accept incoming proxy headers",
    )
    parser.add_argument(
        "--headers",
        nargs='*',
        type=_fmt_kv_pairs,
        help="Custom HTTP response headers as 'Name:Value' pairs",
    )
    return parser


def main(argv=None):
    import uvicorn

    parser = get_parser()
    pargs = parser.parse_args(argv)
    print(f"Starting server with the following options: {vars(pargs)}")
    uvicorn.run('migas_server.app:app', **vars(pargs))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
