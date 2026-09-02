"""New Mexico's tile mart, refreshed by the shared engine.

A shim rather than a deletion: `cr_nm_wellhistory_status_vocab_2` carries this file as its
`code_ref` in the applied migration 071, which also pins
`python -m glasswell.marts.nm_wells --dsn <dsn>` as the rebuild command for the mart it
invalidates, and `glasswell-nm-tiles` resolves here.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

JURISDICTION_CODE = "NM"


def main(argv: Sequence[str] | None = None) -> int:
    from glasswell.ingest.base import resolve_environment  # noqa: F401
    from glasswell.marts.wells import main as engine_main

    # sys.argv when the caller passed nothing, not an empty list: argparse's own default is
    # what a `python -m` invocation relies on, and `argv or []` swallowed --dsn.
    passed = sys.argv[1:] if argv is None else list(argv)
    return engine_main([*passed, "--jurisdiction", JURISDICTION_CODE])


if __name__ == "__main__":
    raise SystemExit(main())
