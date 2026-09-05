"""The served document, judged against the committed snapshot by the differ.

The differ's own rules are asserted over built documents in tests/unit/test_openapi_diff_rules.py,
which needs no database. This is the arm that does: it asks the app what it serves.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tests.contract.openapi_diff import breaking
from tests.contract.test_openapi_snapshot import SNAPSHOT_PATH


def test_the_served_document_is_not_a_breaking_change_against_the_snapshot(
    client: TestClient,
) -> None:
    """The CI mode. The byte gate says something moved; this says whether it costs a /v2."""
    committed = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    served = client.get("/openapi.json").json()

    offenders = breaking(committed, served)

    assert offenders == [], "\n".join(str(change) for change in offenders)
