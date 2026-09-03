"""Montana's tile marts, refreshed by the shared engine.

A shim rather than a deletion: `infra/systemd/glasswell-ingest.service` executes
`python -m glasswell.marts.mt_wells`, and the runbook and the martin README publish the same
spelling. Deleting it would fail `Type=oneshot` on the next timer fire and silently skip every
unit line after it for a whole train.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

# Re-exported: the layer declaration, the tile property and the test that holds the two equal
# all read this name, and the vocabulary is spelled once in the engine.
from glasswell.marts.wells import MAP_STICK  # noqa: F401

JURISDICTION_CODE = "MT"


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
