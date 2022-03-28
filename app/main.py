import sys


def get_parser():
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0", help="hostname")
    parser.add_argument("--port", default=8000, help="server port")
    parser.add_argument("--workers", default=1, help="worker processes")
    parser.add_argument("--reload", action="store_true", help="Reload app on change (dev only)")
    return parser


def main(argv=None):
    import uvicorn

    parser = get_parser()
    pargs = parser.parse_args(argv)
    uvicorn.run('app.server.app:app', **vars(pargs))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
