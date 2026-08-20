"""The snapshot gate (blueprint §3.6.1, SB-04 §7.2): the contract cannot drift silently."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

SNAPSHOT_PATH = Path(__file__).with_name("openapi_snapshot.json")


def served(client: TestClient) -> str:
    return json.dumps(client.get("/openapi.json").json(), indent=2, sort_keys=True) + "\n"


def test_the_served_document_matches_the_committed_snapshot(client: TestClient) -> None:
    assert served(client) == SNAPSHOT_PATH.read_text(encoding="utf-8")
