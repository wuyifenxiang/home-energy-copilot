"""Entry point: ``python -m alexa_mcp``."""

from __future__ import annotations

import argparse
import logging
import os
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
    parser.add_argument(
        "--no-bedrock",
        action="store_true",
        help=(
            "Never call Amazon Bedrock; always use the built-in spoken templates. "
            "Bedrock is only used when ALEXA_MCP_BEDROCK_MODEL and AWS credentials "
            "are set, so this flag is for forcing templates even when they are."
        ),
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

    expose_status = os.environ.get("ALEXA_MCP_EXPOSE_STATUS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    registry = build_registry(db, expose_status=expose_status)

    if args.describe:
        print(describe_registry(registry))
        print(f"\ntool surface fingerprint: {registry_fingerprint(registry)}")
        print(f"bedrock rewriting: {'on' if not args.no_bedrock else 'off'}")
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
        bedrock_rewrite=not args.no_bedrock,
        log_level=getattr(logging, args.log_level.upper(), logging.INFO),
    )

    logger = logging.getLogger("alexa_mcp")
    url = f"http://{args.host}:{args.port}{args.path}"
    logger.info("MCP endpoint ready at %s", url)
    logger.info(
        "protocol %s (also accepts %s)",
        PROTOCOL_VERSION,
        ", ".join(SUPPORTED_PROTOCOL_VERSIONS[1:]),
    )
    logger.info("health check: http://%s:%s/healthz", args.host, args.port)
    logger.info(
        "%d tools: %s", len(app.registry), ", ".join(app.registry.names())
    )

    # Say plainly whether Bedrock is live. Without this line it is impossible to
    # tell "Bedrock is working" from "Bedrock silently fell back to templates".
    if args.no_bedrock:
        logger.info("Amazon Bedrock rewriting: disabled by --no-bedrock")
    else:
        from .bedrock import get_rewriter

        status = get_rewriter().status()
        if status["active"]:
            logger.info(
                "Amazon Bedrock rewriting: ON (%s in %s)",
                status["model"],
                status["region"],
            )
        else:
            missing = []
            if not status["model"]:
                missing.append("ALEXA_MCP_BEDROCK_MODEL")
            if status["credentialSource"] == "none":
                missing.append("AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY")
            logger.info(
                "Amazon Bedrock rewriting: off (templates in use; set %s to enable)",
                " and ".join(missing) or "credentials",
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
