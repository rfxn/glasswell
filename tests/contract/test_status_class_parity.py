"""The class domain, held to itself in three places: the migration, the seed and the wire.

The domain exists to stop three copies agreeing by coincidence, so the first thing to gate is
that its own two writers and the response built from them say the same thing, on the clock and
the evidence as well as on the symbology.

Three of §7's standing gates live here too, because no constraint in the migration can reach
them. Completeness and minimality are about the *registered* set rather than about the five maps
that carry a foreign key, so a sixth map registered without one is visible; and neutrality is a
property of prose, which is what keeps a class note from arguing from one regulator's letters
while another's codes sit in the same class.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.types.json import Jsonb

from glasswell.lineage.jurisdictions import load_jurisdictions
from glasswell.lineage.status_classes import load_status_classes
from glasswell.seed.conformance_status_classes import (
    ABSENCE_BASIS_RULE_ID,
    CLASS_DOMAIN_RULE_ID,
    CONTRAST_EXCEPTIONS,
    CONTRAST_EXCEPTIONS_ROUTED_TO,
)
from glasswell.seed.status_classes import DOMAIN_EFFECTIVE_FROM, STATUS_CLASSES, class_parameters
from glasswell.status_resolution import served_vocabularies, status_map_classes

pytestmark = pytest.mark.contract

PATH = "/v1/jurisdictions"
COMPARED = (
    "status_canonical",
    "label",
    "colour",
    "glyph",
    "min_zoom",
    "sort_order",
    "is_absence",
    "note",
    "rule_id",
)
# Zero rows and no serving rule names it, so a constraint on it would be a claim about a table
# nothing writes. Listed by name rather than skipped silently, which is what makes its deadness
# visible on the day someone starts writing to it.
EXEMPT_MAPS = ("nm_status_map",)
# Every mapped class is produced by at least one registered map today, so this ships empty. A
# class added for a state that never lands would have to be named here.
UNPRODUCED_CLASSES: tuple[str, ...] = ()


def served(client: TestClient) -> dict[str, Any]:
    response = client.get(PATH, params={"limit": 100})
    assert response.status_code == 200
    return response.json()


def domain_rows(client: TestClient) -> list[dict[str, Any]]:
    return served(client)["meta"]["status_classes"]


def test_the_migration_the_seed_and_the_wire_carry_one_domain(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """N-5's shape: the clock and the evidence are compared too, so a repoint that touches one
    writer and forgets the other reddens here rather than on the deployed host."""
    resident = load_status_classes(seeded)
    declared = [class_parameters(row) for row in STATUS_CLASSES]
    wire = domain_rows(client)

    assert len(resident) == len(declared) == len(wire)
    for landed, stated, sent in zip(resident, declared, wire, strict=True):
        for column in COMPARED:
            assert getattr(landed, column) == stated[column], column
            assert sent[column] == stated[column], column
        assert landed.effective_from == DOMAIN_EFFECTIVE_FROM
        assert landed.published_at == DOMAIN_EFFECTIVE_FROM


def test_the_wire_serves_the_domain_once_in_legend_order_citing_two_rules(
    client: TestClient,
) -> None:
    """In `meta` and not in `data`: the domain is not a jurisdiction, and a twelfth element that
    is not one would break every `/*/` allowlist pointer and the cursor the operation carries."""
    body = served(client)
    wire = body["meta"]["status_classes"]

    assert [row["sort_order"] for row in wire] == sorted(row["sort_order"] for row in wire)
    assert all("status_canonical" not in row for row in body["data"])
    absent = [row for row in wire if row["is_absence"]]
    assert len(absent) == 1
    assert absent[0]["rule_id"] == ABSENCE_BASIS_RULE_ID
    assert {row["rule_id"] for row in wire if not row["is_absence"]} == {CLASS_DOMAIN_RULE_ID}


def test_each_jurisdiction_serves_the_classes_its_own_map_produces(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """North Dakota is the only registration whose codebook produces `confidential`, and that is
    a fact about its codebook rather than about the domain."""
    body = served(client)
    rows = {row["jurisdiction_code"]: row for row in body["data"]}
    measured = {item.jurisdiction_code: item for item in served_vocabularies(seeded)}
    domain = {row["status_canonical"] for row in body["meta"]["status_classes"]}

    assert set(rows) == set(measured)
    for code, row in rows.items():
        vocabulary = row["vocabulary"]
        assert vocabulary["rule_id"] == measured[code].rule_id
        assert vocabulary["resolved_at"] == measured[code].resolved_at
        assert vocabulary["unmapped_action"] == measured[code].unmapped_action
        assert vocabulary["classes"] == list(measured[code].classes)
        assert set(vocabulary["classes"]) <= domain

    holders = [code for code, row in rows.items() if "confidential" in row["vocabulary"]["classes"]]
    assert holders == ["ND"]


def test_the_registration_serves_its_legend_note_and_its_presentation(
    client: TestClient,
) -> None:
    """The note moves onto the wire so the client stops reading it from a generated module and
    a jurisdiction's own sentence can change without a rebuild."""
    rows = {row["jurisdiction_code"]: row for row in served(client)["data"]}

    assert rows["CO"]["vocabulary"]["legend_note"]
    assert [code for code, row in rows.items() if row["vocabulary"]["legend_note"]] == ["CO"]
    assert rows["ND"]["map"]["wells_draw_order"] == 40
    assert rows["ND"]["capabilities"]["explorer_default"] is True
    assert [code for code, row in rows.items() if row["capabilities"]["explorer_default"]] == [
        "ND"
    ]
    assert rows["ND"]["rationale"]


def test_gate_a_every_class_a_registered_map_produces_is_a_domain_row(
    seeded: psycopg.Connection,
) -> None:
    """The foreign keys cover the five maps that carry one. This covers the *registered* set, so
    a sixth map registered without a constraint reddens here rather than when a well draws grey."""
    domain = {row.status_canonical for row in load_status_classes(seeded)}

    assert set(status_map_classes(seeded)) <= domain


def test_gate_a_reddens_against_a_map_registered_without_a_constraint(
    seeded: psycopg.Connection,
) -> None:
    """The planted violation is a *registered* relation with no foreign key, which is the only
    shape the five keys cannot refuse."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "create table lineage.planted_status_map"
            " (status text primary key, status_canonical text)"
        )
        cursor.execute(
            "insert into lineage.planted_status_map values ('ZZ', 'planted_class')"
        )
        cursor.execute(
            "insert into lineage.conformance_rule_publications"
            " (rule_id, published_vintage, evidence_tag, evidence_commit)"
            " values ('cr_planted_status_vocab_1', current_date, 'harness-fixture', %s)",
            ("0" * 40,),
        )
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, source_id, stage,"
            " applies_to_fields, rule_kind, spec, rule, rationale, effective_from,"
            " published_vintage) values ('cr_planted_status_vocab_1', 'cr_planted_status_vocab',"
            " 'nd_mpr_xlsx', 'conform', array['status']::text[], 'vocab_map', %s,"
            " 'planted', 'planted', current_date, current_date)",
            (
                Jsonb(
                    {
                        "mapping_table": "planted_status_map",
                        "key_col": "status",
                        "value_col": "status_canonical",
                    }
                ),
            ),
        )
        # A sixth registration rather than a second rule on an existing one: a partial unique
        # index holds status_vocabulary to one serving rule per registration instant, which is
        # itself part of what makes the registered set the right scope for this gate.
        cursor.execute(
            "insert into lineage.jurisdiction_codes values ('ZZ', 'state')"
        )
        cursor.execute(
            "insert into lineage.jurisdictions (jurisdiction_code, effective_from,"
            " published_at, evidence_tag, evidence_commit, name, regulator_name, regulator_url,"
            " identity_scheme, identity_prefix, identity_pattern, source_ids, rationale)"
            " values ('ZZ', current_date, current_date, 'harness-fixture', %s, 'Planted',"
            " 'regulator', 'https://example.invalid/', 'api10', '99', '^99[0-9]{8}$',"
            " array['nd_mpr_xlsx'], 'planted')",
            ("0" * 40,),
        )
        cursor.execute(
            "insert into lineage.jurisdiction_rules (jurisdiction_code, effective_from,"
            " published_at, decision, rule_id)"
            " values ('ZZ', current_date, current_date, 'status_vocabulary',"
            " 'cr_planted_status_vocab_1')"
        )
    domain = {row.status_canonical for row in load_status_classes(seeded)}

    assert "planted_class" in set(status_map_classes(seeded))
    assert not set(status_map_classes(seeded)) <= domain


def test_gate_b_every_mapped_class_is_produced_by_a_registered_map(
    seeded: psycopg.Connection,
) -> None:
    """Minimality. A class in the domain that no registered map produces is a class added for a
    state that never landed, and it has to be named rather than left to be noticed."""
    produced = set(status_map_classes(seeded))
    mapped = {row.status_canonical for row in load_status_classes(seeded) if not row.is_absence}

    assert sorted(mapped - produced) == sorted(UNPRODUCED_CLASSES)


def test_gate_b_reddens_against_a_class_no_registered_map_produces(
    seeded: psycopg.Connection,
) -> None:
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into lineage.status_classes (status_canonical, label, colour, glyph,"
            " min_zoom, sort_order, note, rule_id, effective_from, published_at, rationale)"
            " values ('planted_class', 'Planted', '#010203', 'solid', 4, 999, 'planted',"
            " %s, %s, %s, 'planted')",
            (CLASS_DOMAIN_RULE_ID, DOMAIN_EFFECTIVE_FROM, DOMAIN_EFFECTIVE_FROM),
        )
    produced = set(status_map_classes(seeded))
    mapped = {row.status_canonical for row in load_status_classes(seeded) if not row.is_absence}

    assert sorted(mapped - produced) != sorted(UNPRODUCED_CLASSES)


def test_gate_d_no_class_note_names_a_registered_jurisdiction(
    seeded: psycopg.Connection,
) -> None:
    """This is what stops §2.4's re-authoring rotting back: today nine of the eleven notes in the
    client argue from one regulator's letters while a third regulator's codes sit in the class."""
    forbidden = jurisdiction_words(seeded)

    for row in load_status_classes(seeded):
        named = [word for word in forbidden if word in row.note]
        assert named == [], f"{row.status_canonical} names {named}"


def test_gate_d_reddens_against_a_note_that_names_one(seeded: psycopg.Connection) -> None:
    forbidden = jurisdiction_words(seeded)
    planted = f"The {sorted(forbidden)[0]} case, argued from one regulator's codebook."

    assert [word for word in forbidden if word in planted] != []


def jurisdiction_words(connection: psycopg.Connection) -> set[str]:
    """Every registered name, code and identity prefix, which is what a note may not carry."""
    registry = load_jurisdictions(connection)
    words = set()
    for row in registry:
        words.add(row.name)
        words.add(row.jurisdiction_code)
        if row.identity_prefix is not None:
            words.add(row.identity_prefix)
    return words


# The client's own contrast gate, read where it is written. A `Record<string, readonly
# string[]>` object literal, parsed rather than imported because the two tiers do not share a
# loader; the same shape `test_jurisdiction_seed.py` reads `status.ts` with.
CONTRAST_GATE = Path(__file__).resolve().parents[2] / "web/src/map/status-contrast.test.ts"
_CARRIED_FORWARD = re.compile(
    r"CARRIED_FORWARD: Readonly<Record<string, readonly string\[\]>> = \{(.*?)\n\};", re.S
)
_EXCEPTION = re.compile(r'(\w+):\s*\[(.*?)\]', re.S)


def carried_forward_in_the_client() -> dict[str, list[str]]:
    block = _CARRIED_FORWARD.search(CONTRAST_GATE.read_text(encoding="utf-8"))
    assert block, "the client contrast gate no longer declares CARRIED_FORWARD by that name"
    return {
        name: [value.strip().strip('"') for value in values.split(",") if value.strip()]
        for name, values in _EXCEPTION.findall(block.group(1))
    }


def test_the_published_bar_states_the_classes_it_does_not_hold_for(
    seeded: psycopg.Connection,
) -> None:
    """H-11: a reader resolving this rule was told the domain clears 3:1 against four
    backgrounds, and for three of twelve classes on the light theme that is false.

    The exceptions are published beside the bar and held equal to the client gate that carries
    them, so the two lists are one decision rather than two that agree by coincidence.
    """
    with seeded.cursor() as cursor:
        cursor.execute(
            "select spec from lineage.conformance_rules where rule_id = %s",
            (CLASS_DOMAIN_RULE_ID,),
        )
        spec = cursor.fetchone()[0]

    assert spec["min_contrast_ratio"] == 3.0
    assert spec["min_contrast_exceptions"] == CONTRAST_EXCEPTIONS
    assert spec["min_contrast_exceptions_routed_to"] == CONTRAST_EXCEPTIONS_ROUTED_TO
    assert carried_forward_in_the_client() == CONTRAST_EXCEPTIONS
    # Not vacuous: every substrate named is one the rule says the bar is measured against.
    for substrates in spec["min_contrast_exceptions"].values():
        assert substrates
        for where in substrates:
            assert where in {"dark panel", "dark map", "light panel", "light map"}


def test_the_domains_own_rules_resolve_at_conformance(client: TestClient) -> None:
    """N-6. §2.6's checklist item 3 warns that a mis-dated vintage serves 404 for a rule, and
    these two are the rules every served class cites."""
    for rule_id in (CLASS_DOMAIN_RULE_ID, ABSENCE_BASIS_RULE_ID):
        response = client.get(f"/v1/conformance/{rule_id}")

        assert response.status_code == 200, rule_id
        assert response.json()["data"]["rationale"]


def test_the_counts_still_resolve_to_a_manifest(client: TestClient) -> None:
    """The additions are additive: every figure this surface already served still explains."""
    body = client.get(PATH, params={"limit": 100, "explain": "true"}).json()
    measured = [row for row in body["data"] if row["well_count"] is not None]

    assert measured
    for row in measured:
        assert body["_explain"][row["well_count"]["d"]]


ROUTERS = Path(__file__).resolve().parents[2] / "src" / "glasswell" / "api" / "routers"


def reported_codes(connection: psycopg.Connection) -> set[str]:
    """Every code a registered map keys on: what a router arm would have to name to be one."""
    codes: set[str] = set()
    with connection.cursor() as cursor:
        cursor.execute(
            "select c.spec->>'mapping_table', c.spec->>'key_col'"
            "  from lineage.conformance_rules c"
            " where c.spec->>'mapping_table' is not null and c.spec->>'key_col' is not null"
        )
        for table, column in cursor.fetchall():
            cursor.execute(
                sql.SQL("select distinct {column}::text from lineage.{table}").format(
                    column=sql.Identifier(column), table=sql.Identifier(table)
                )
            )
            codes.update(str(value) for (value,) in cursor.fetchall() if value)
    return codes


def translations_in(text: str, codes: set[str]) -> list[str]:
    """A `case`/`when` arm or a dict key naming a code a registered map already decides."""
    found = []
    for code in codes:
        for shape in (f"when '{code}'", f'when "{code}"', f'"{code}":', f"'{code}':"):
            if shape in text:
                found.append(shape)
    return sorted(found)


def test_gate_e_no_router_translates_a_reported_status_into_a_class(
    seeded: psycopg.Connection,
) -> None:
    """One resolver, and nowhere else. A mart-only resolver leaves the API serving null; an
    API-only one leaves the tiles serving null; a second arm in a router leaves the tile a
    reader clicks and the card they land on able to answer differently on one screen."""
    codes = reported_codes(seeded)
    assert codes, "an empty code set would pass this on nothing"

    offenders = {
        path.name: translations_in(path.read_text(encoding="utf-8"), codes)
        for path in sorted(ROUTERS.glob("*.py"))
        if translations_in(path.read_text(encoding="utf-8"), codes)
    }

    assert offenders == {}


def test_gate_e_reddens_against_a_planted_arm(seeded: psycopg.Connection) -> None:
    """A negative fixture drawn from a shape the rule does not name: the arm is planted in a
    scratch copy of the router text rather than in the tree, so the gate is shown reading."""
    codes = reported_codes(seeded)
    planted = "    status = case when 'PLUGGED' then 'plugged' end\n"

    assert "PLUGGED" in codes
    assert translations_in(planted, codes) == ["when 'PLUGGED'"]
