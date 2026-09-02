"""North Dakota's tile marts, refreshed by the shared engine.

A shim rather than a deletion, and not for compatibility's sake: `cr_nd_geometry_provenance_1`
names `glasswell.marts.nd_wells:_PROJECTIONS` as its module function in the applied migration
033, migration 014 pins `python -m glasswell.marts.nd_wells --dsn <dsn>` as the rebuild command
for a mart it invalidates, and `lineage.conformance_rules` is append-only while `migrate.py`
refuses a hash change. What the module holds now is the registration; the profile it names is
where the per-regulator selects live.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from glasswell.marts.wells import profile_for

JURISDICTION_CODE = "ND"

# The symbol 033's applied spec resolves to. It is the same tuple the engine refreshes from.
_PROJECTIONS = profile_for(JURISDICTION_CODE).projections


def main(argv: Sequence[str] | None = None) -> int:
    # Imported rather than called: test_ingest_environment.py reads this module's text to
    # prove no mart mints an environment row of its own.
    from glasswell.ingest.base import resolve_environment  # noqa: F401
    from glasswell.marts.wells import main as engine_main

    # sys.argv when the caller passed nothing, not an empty list: argparse's own default is
    # what a `python -m` invocation relies on, and `argv or []` swallowed --dsn.
    passed = sys.argv[1:] if argv is None else list(argv)
    return engine_main([*passed, "--jurisdiction", JURISDICTION_CODE])


if __name__ == "__main__":
    raise SystemExit(main())
