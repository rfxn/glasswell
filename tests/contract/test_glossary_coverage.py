"""R9 / DIR-8 coverage: every term the API names or the frontend binds resolves to a row."""

from __future__ import annotations

import re
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.api.examples import EXAMPLE_API10
from glasswell.seed.glossary import seed_glossary
from tests.contract.test_naked_numbers import exercised

GLOSSARY_EXTENSION = "x-glasswell-glossary"

WEB_SOURCE = Path(__file__).resolve().parents[2] / "web" / "src"
BOUND_TERM = re.compile(r'"(gt_[a-z0-9_]+)"')

# One resident term, re-stated. The seeder keys on term_id, so the term text is what pins the
# row this rewrites: "PLSS" is already seeded and slugs to gt_plss.
RESEED = """
- term: PLSS
  aliases: ["Public Land Survey System", "Rectangular survey system"]
  short_definition: >-
    The township, range and section grid, re-stated to prove a correction reaches a reader.
  expanded_definition: >-
    A definition sitting corrected in the seed file and stale in the database is the drift the
    upsert exists to close.
  domain_tags: [geospatial, governance]
  related_terms: ["Land unit"]
  source_refs: ["blueprint-v0.6 §9", "cr_blm_plss_publisher_1"]
  highlightable: false
"""


@pytest.fixture
def reseeded(seeded: psycopg.Connection, tmp_path: Path) -> psycopg.Connection:
    """Re-runs the seeder over one already-resident term, from a seed file this test owns."""
    path = tmp_path / "reseed.yml"
    path.write_text(RESEED, encoding="utf-8")
    seed_glossary(seeded, path)
    seeded.commit()
    return seeded


@pytest.fixture
def term_ids(seeded: psycopg.Connection) -> set[str]:
    with seeded.cursor() as cursor:
        cursor.execute("select term_id from canonical.glossary_terms")
        return {row[0] for row in cursor.fetchall()}


def test_every_label_the_api_emits_resolves(client: TestClient, term_ids: set[str]) -> None:
    """A label pointing at a term that does not exist is a broken hover, silently."""
    emitted: dict[str, str] = {}
    for _, call in exercised(client):
        response = client.get(call["url"], params=call["params"])
        if not response.headers["content-type"].startswith("application/json"):
            continue
        body = response.json()
        if isinstance(body, dict) and "meta" in body:
            emitted |= body["meta"]["labels"]

    assert emitted, "no response bound a field to a glossary term"
    assert {value for value in emitted.values() if value not in term_ids} == set()


def test_every_schema_binding_resolves(client: TestClient, term_ids: set[str]) -> None:
    document = client.get("/openapi.json").json()
    bound = _bindings(document)

    assert bound
    assert bound - term_ids == set()


def test_every_term_the_frontend_binds_by_hand_resolves(term_ids: set[str]) -> None:
    """A bound id never travels in a response, so the two tests above cannot see it.

    The surfaces that bind one are gated for what they teach in
    web/src/glossary/coverage.test.ts; this is the half of that gate the seed owns.
    """
    bound: set[str] = set()
    for path in sorted(WEB_SOURCE.rglob("*.ts")):
        if path.name.endswith((".test.ts", "fixtures.ts")):
            continue
        bound |= set(BOUND_TERM.findall(path.read_text(encoding="utf-8")))

    assert bound, "no frontend surface binds a term by hand, or this test cannot fail"
    assert bound - term_ids == set()


def test_a_reseeded_alias_is_served(client: TestClient, reseeded: psycopg.Connection) -> None:
    """The glossary is reference data: a re-seed corrects a resident row, never skips it."""
    served = client.get("/v1/glossary", params={"q": "Rectangular survey system"}).json()["data"]

    assert [row["term_id"] for row in served] == ["gt_plss"]
    assert "Rectangular survey system" in served[0]["aliases"]
    assert "re-stated to prove a correction reaches a reader" in served[0]["short_definition"]


def test_a_reseeded_row_carries_its_new_evidence_and_flag(
    client: TestClient, reseeded: psycopg.Connection
) -> None:
    detail = client.get("/v1/glossary/gt_plss").json()["data"]
    index = client.get("/v1/glossary/index").json()["data"]

    assert detail["source_refs"] == ["blueprint-v0.6 §9", "cr_blm_plss_publisher_1"]
    assert detail["highlightable"] is False
    # A term the seed turns off is served as stopwords, never as scannable entries (M7).
    assert "rectangular survey system" in index["stopwords"]
    assert [entry for entry in index["entries"] if entry["term_id"] == "gt_plss"] == []


def test_reseeding_adds_no_row_and_loses_none(
    client: TestClient, seeded: psycopg.Connection, tmp_path: Path
) -> None:
    before = client.get("/v1/glossary", params={"limit": 200}).json()["data"]
    path = tmp_path / "reseed.yml"
    path.write_text(RESEED, encoding="utf-8")
    total = seed_glossary(seeded, path)
    seeded.commit()

    after = client.get("/v1/glossary", params={"limit": 200}).json()["data"]
    assert total == len(before)
    assert [row["term_id"] for row in after] == [row["term_id"] for row in before]


def test_labels_are_json_pointers(client: TestClient) -> None:
    labels = client.get(f"/v1/wells/{EXAMPLE_API10}").json()["meta"]["labels"]

    assert labels, "the well detail bound no field to a term, or this test cannot fail"
    assert all(pointer.startswith("/") for pointer in labels)


def _bindings(node: object) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        binding = node.get(GLOSSARY_EXTENSION)
        if isinstance(binding, str):
            found.add(binding)
        for value in node.values():
            found |= _bindings(value)
    elif isinstance(node, list):
        for value in node:
            found |= _bindings(value)
    return found
