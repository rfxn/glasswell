"""Where a command-line entry point gets its database DSN, and why it is not on the argv.

A DSN passed as an argument is visible in `/proc` to every user on the box and lands in shell
history; `scripts/smoke.sh` states the same principle for the owner key. So `--dsn` is optional
everywhere and the fallback is the one the API, the collector and the principal resolver
already use: `GLASSWELL_DSN`, then `DATABASE_URL`. The pipeline units set the first with a
password-free socket DSN, which is what makes the flag unnecessary rather than merely optional.
"""

from __future__ import annotations

import argparse
import os

DSN_ENV = "GLASSWELL_DSN"
FALLBACK_DSN_ENV = "DATABASE_URL"
MISSING = f"no database DSN: pass --dsn, or set {DSN_ENV} or {FALLBACK_DSN_ENV}"


def add_dsn_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dsn",
        default=None,
        help=f"database DSN; defaults to ${DSN_ENV}, then ${FALLBACK_DSN_ENV}",
    )


def resolve_dsn(explicit: str | None = None) -> str:
    """The DSN this process should use, or a refusal naming both variables it looked at."""
    dsn = explicit or os.environ.get(DSN_ENV) or os.environ.get(FALLBACK_DSN_ENV)
    if not dsn:
        raise SystemExit(MISSING)
    return dsn
