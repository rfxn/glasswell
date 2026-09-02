"""Texas's tile marts, refreshed by the shared engine.

A shim rather than a deletion. No applied migration names this module, but `python -m
glasswell.marts.tx_wells` is the spelling the runbooks and the operational callers publish, and
a deletion would fail on the next run of whatever still types it.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

JURISDICTION_CODE = "TX"


def main(argv: Sequence[str] | None = None) -> int:
    # Imported rather than called: test_ingest_environment.py reads a mart module's text to
    # prove no mart mints an environment row of its own.
    from glasswell.ingest.base import resolve_environment  # noqa: F401
    from glasswell.marts.wells import main as engine_main

    # sys.argv when the caller passed nothing, not an empty list: argparse's own default is
    # what a `python -m` invocation relies on, and `argv or []` swallowed --dsn.
    passed = sys.argv[1:] if argv is None else list(argv)
    return engine_main([*passed, "--jurisdiction", JURISDICTION_CODE])


if __name__ == "__main__":
    raise SystemExit(main())
