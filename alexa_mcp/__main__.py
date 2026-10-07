"""Entry point: ``python -m alexa_mcp``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .server import (
    DEFAULT_ENDPOINT_PATH,
    DEFAULT_HOST,
    DEFAULT_PORT,
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    create_server,
)
from .store import Database, seed_demo_home
from .tools import build_registry, describe_registry, registry_fingerprint

INSTRUCTIONS = """\
This server powers a home energy assistant. Prefer get_home_status and
get_energy_report before recommending anything. Money is spoken as currency and
never with more than two decimals. Anything that changes the home must be
proposed first and applied only after the customer agrees.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alexa_mcp",
        description=(
            "Self-hosted MCP server for the Alexa+ track of the Amazon Developer "
            f"Hackathon 2026 (protocol revision {PROTOCOL_VERSION})."
        ),
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind address (default 127.0.0.1).")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP port (default 8765).")
    parser.add_argument(
        "--path",
        default=DEFAULT_ENDPOINT_PATH,
        help="MCP endpoint path (default /mcp).",
    )
    parser.add_argument(
        "--db",
        default="data/home.db",
        help="SQLite file for home state, or ':memory:' (default data/home.db).",
    )
    parser.add_argument(
        "--allowed-origin",
        action="append",
        default=[],
        help="Exact Origin allowed in addition to localhost. Repeatable.",
    )
    parser.add_argument(
        "--describe",
        action="store_true",
        help="Print the tool surface and exit without starting the server.",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Skip seeding the demo home.",
    )
    parser.add_argument("--log-level", default="INFO", help="DEBUG, INFO, WARNING, ERROR.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _package_visible() -> bool:
    """True when the directory containing the ``alexa_mcp`` package is importable."""
    for entry in sys.path:
        if not entry:
            continue
        try:
            if (Path(entry) / "alexa_mcp" / "__main__.py").is_file():
                return True
        except OSError:
            continue
    return False


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # A packaged console script would not need this, but a zero-install
    # submission does: if the package directory is not on sys.path the user is
    # running this from the wrong directory. Fail with instructions rather than
    # letting Python emit a bare "No module named alexa_mcp".
    if not _package_visible():
        print(
            "error: could not find the alexa_mcp package on sys.path.\n"
            "Run this from the repository root:\n"
            "    cd <path to this repo>\n"
            "    python -m alexa_mcp --describe\n"
            "Bundled scripts work from any directory:\n"
            "    python <path to this repo>/tests/smoke_test.py",
            file=sys.stderr,
        )
        return 2

    db = Database(":memory:" if args.db == ":memory:" else args.db)
    if not args.no_seed:
        seed_demo_home(db)

    registry = build_registry(db)

    if args.describe:
        print(describe_registry(registry))
        print(f"\ntool surface fingerprint: {registry_fingerprint(registry)}")
        return 0

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(
            f"warning: binding to {args.host}. The MCP specification recommends "
            "localhost for local servers; make sure authentication is in front of "
            "this endpoint before exposing it.",
            file=sys.stderr,
        )

    httpd, app = create_server(
        registry,
        host=args.host,
        port=args.port,
        endpoint_path=args.path,
        allowed_origins=tuple(args.allowed_origin),
        version=__version__,
        instructions=INSTRUCTIONS,
        log_level=getattr(logging, args.log_level.upper(), logging.INFO),
    )

    url = f"http://{args.host}:{args.port}{args.path}"
    logging.getLogger("alexa_mcp").info("MCP endpoint ready at %s", url)
    logging.getLogger("alexa_mcp").info(
        "protocol %s (also accepts %s)",
        PROTOCOL_VERSION,
        ", ".join(SUPPORTED_PROTOCOL_VERSIONS[1:]),
    )
    logging.getLogger("alexa_mcp").info(
        "health check: http://%s:%s/healthz", args.host, args.port
    )
    logging.getLogger("alexa_mcp").info(
        "%d tools: %s", len(app.registry), ", ".join(app.registry.names())
    )

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logging.getLogger("alexa_mcp").info("shutting down")
    finally:
        httpd.server_close()
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
