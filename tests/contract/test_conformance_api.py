"""`/v1/conformance`: every mapping decision with its rationale and its evidence (R8, S11)."""

from __future__ import annotations

import re
from datetime import date

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.api.deps import today
from glasswell.api.examples import EXAMPLE_DERIVATION_ID, EXAMPLE_RULE_ID
from glasswell.api.pagination import decode_cursor, query_fingerprint
from glasswell.seed.conformance_basin_context import BASIN_CONTEXT_RULES
from glasswell.seed.conformance_basins import BASIN_RULES
from glasswell.seed.conformance_co import CO_RULES
from glasswell.seed.conformance_fracfocus import FRACFOCUS_RULES
from glasswell.seed.conformance_land import LAND_RULES
from glasswell.seed.conformance_mt import MT_RULES
from glasswell.seed.conformance_nd import ND_RULES
from glasswell.seed.conformance_nm import NM_RULES
from glasswell.seed.conformance_nm_wells import NM_WELLS_GIS_RULES, NM_WELLS_RULES
from glasswell.seed.conformance_producing import PRODUCING_RULES
from glasswell.seed.conformance_schedules import SCHEDULE_RULES
from glasswell.seed.conformance_status_history import (
    HISTORY_RULES as STATUS_HISTORY_RULES,
)
from glasswell.seed.conformance_tx import ALLOCATION_RULES, TX_RULES
from glasswell.seed.conformance_typecurve import TYPECURVE_RULES
from glasswell.seed.conformance_vintage import VINTAGE_RULES
from tests.support.scripts import load_script

# The pair a branch registers before its train is cut. The API serves it as it stands, and
# `release.py` is what refuses to tag while a migration still carries it.
_release = load_script("gw_release_for_conformance", "release.py")
PLACEHOLDER_TAG: str = _release.PLACEHOLDER_EVIDENCE_TAG
PLACEHOLDER_COMMIT: str = _release.PLACEHOLDER_EVIDENCE_COMMIT

SEEDED_RULES = 14


def test_every_seeded_rule_is_served(client: TestClient) -> None:
    data = client.get("/v1/conformance", params={"limit": 200}).json()["data"]

    assert len(data) >= SEEDED_RULES


def test_every_rule_carries_a_rationale_and_evidence(client: TestClient) -> None:
    """Smoke check 10 asserts this off-box; assert it here so it cannot regress first."""
    data = client.get("/v1/conformance", params={"limit": 200}).json()["data"]

    assert len(data) >= SEEDED_RULES, "the registry served no rule, or this test cannot fail"
    assert all(item["rationale"] for item in data)
    assert all(item["evidence_url"] for item in data)
    assert all(item["published_vintage"] for item in data)


def test_rules_are_ordered_newest_effective_first(client: TestClient) -> None:
    data = client.get("/v1/conformance", params={"limit": 200}).json()["data"]

    keys = [(item["effective_from"], item["rule_id"]) for item in data]
    assert keys == sorted(keys, key=lambda key: (key[0], key[1]), reverse=True)


def test_the_collection_filters_on_source_and_kind(client: TestClient) -> None:
    data = client.get(
        "/v1/conformance", params={"source_id": "nd_gis_wells", "kind": "vocab_map"}
    ).json()["data"]

    assert data
    assert {item["source_id"] for item in data} == {"nd_gis_wells"}
    assert {item["rule_kind"] for item in data} == {"vocab_map"}


def test_the_collection_filters_on_stage(client: TestClient) -> None:
    data = client.get("/v1/conformance", params={"stage": "validate"}).json()["data"]

    assert data
    assert {item["stage"] for item in data} == {"validate"}


def test_the_detail_serves_the_spec_verbatim(client: TestClient) -> None:
    data = client.get(f"/v1/conformance/{EXAMPLE_RULE_ID}").json()["data"]

    assert data["rule_id"] == EXAMPLE_RULE_ID
    assert data["spec"]
    assert data["rule"]
    assert data["evidence_url"].startswith("https://")
    assert data["published_vintage"] == "2026-08-20"


def _served_evidence(client: TestClient, rule_id: str) -> tuple[str, str]:
    data = client.get(f"/v1/conformance/{rule_id}").json()["data"]
    return data["evidence_tag"], data["evidence_commit"]


def _assert_whole_state(tag: str, commit: str, rule_id: str) -> None:
    """A publication pair is repointed or it is the placeholder pair; never one of each."""
    if tag == PLACEHOLDER_TAG:
        assert commit == PLACEHOLDER_COMMIT, f"{rule_id}: UNRELEASED beside a real commit"
    else:
        assert commit != PLACEHOLDER_COMMIT, f"{rule_id}: a tag beside the placeholder commit"
        assert re.fullmatch(r"[0-9a-f]{40}", commit), f"{rule_id}: {commit!r} is not a sha"


def test_a_repointed_publication_serves_its_tag_and_the_commit_it_resolves_to(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """R8 serves the rationale and the effective date. Which release first carried the rule
    is the same kind of fact and lived only in `lineage.conformance_rule_publications`, so a
    reader could see when a decision applied but not which shipped code it applied in.
    The example rule is in the registry, so its row has been through a merge train: a real
    tag and a real commit, and the placeholder pair satisfies neither."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select evidence_tag, evidence_commit from lineage.conformance_rule_publications"
            " where rule_id = %s",
            (EXAMPLE_RULE_ID,),
        )
        stored = cursor.fetchone()

    served = _served_evidence(client, EXAMPLE_RULE_ID)

    assert served == stored
    assert served[0] != PLACEHOLDER_TAG
    assert served[1] != PLACEHOLDER_COMMIT
    assert re.fullmatch(r"[0-9a-f]{40}", served[1])


def test_an_unrepointed_publication_serves_the_placeholder_pair_and_nothing_else(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """A branch registers the placeholder pair because merge order decides the tag. The API
    serves it as it stands -- not null, not a guessed tag -- and `release.py` is what keeps it
    out of a cut release. The pair travels together: the served shape says UNRELEASED only
    beside forty zeros."""
    rule_id = "cr_contract_unrepointed_1"
    _publish_rule(
        seeded,
        rule_id=rule_id,
        published_vintage=date(2026, 1, 1),
        evidence=(PLACEHOLDER_TAG, PLACEHOLDER_COMMIT),
    )

    served = _served_evidence(client, rule_id)

    assert served == (PLACEHOLDER_TAG, PLACEHOLDER_COMMIT)
    _assert_whole_state(*served, rule_id)


def test_a_rule_without_a_publication_row_cannot_enter_the_registry(
    seeded: psycopg.Connection,
) -> None:
    """The third state does not exist to serve. `conformance_rules.published_vintage` is not
    null and is a foreign key into the publications table, and the insert trigger refuses a
    rule with no row there (049) -- so the detail's join never finds nothing, and a null pair
    would mean the schema had been bypassed, not that a rule was unpublished."""
    with pytest.raises(psycopg.errors.CheckViolation, match="no publication evidence"):
        _publish_rule(
            seeded,
            rule_id="cr_contract_unpublished_1",
            published_vintage=date(2026, 1, 1),
            evidence=None,
        )
    seeded.rollback()


def test_every_publication_pair_the_registry_carries_reaches_its_rule_whole(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    """One rule would pass on a constant. One rule per distinct stored pair cannot, and each
    served pair is checked as a whole state, so a half-repointed row -- a tag beside the
    placeholder commit, or the reverse -- reds here rather than reading as evidence."""
    with seeded.cursor() as cursor:
        cursor.execute(
            "select min(r.rule_id), p.evidence_tag, p.evidence_commit"
            "  from lineage.conformance_rule_publications p"
            "  join lineage.conformance_rules r on r.rule_id = p.rule_id"
            " where r.published_vintage <= current_date"
            " group by p.evidence_tag, p.evidence_commit"
            " order by p.evidence_tag, p.evidence_commit"
        )
        published = cursor.fetchall()

    assert len(published) > 1, "the registry carries one pair; this test cannot fail"
    for rule_id, tag, commit in published:
        served = _served_evidence(client, rule_id)
        assert served == (tag, commit), rule_id
        _assert_whole_state(*served, rule_id)


def test_the_collection_leaves_the_evidence_pair_to_the_detail(client: TestClient) -> None:
    """The page is the mapping policy at a glance; the publication pair is a per-rule fact and
    stays where a reader asks for one rule. Additive on the detail only (S1 freeze)."""
    data = client.get("/v1/conformance", params={"limit": 5}).json()["data"]

    assert data
    assert all("evidence_tag" not in item for item in data)


def test_include_applied_by_is_the_reverse_index(client: TestClient) -> None:
    """U21: which derivations cited this rule is one index scan on derivation_rules."""
    data = client.get(
        f"/v1/conformance/{EXAMPLE_RULE_ID}", params={"include": "applied_by"}
    ).json()["data"]

    assert [entry["derivation_id"] for entry in data["applied_by"]] == [EXAMPLE_DERIVATION_ID]


def test_applied_by_is_absent_unless_asked_for(client: TestClient) -> None:
    data = client.get(f"/v1/conformance/{EXAMPLE_RULE_ID}").json()["data"]

    assert "applied_by" not in data


def test_an_unknown_rule_is_not_found(client: TestClient) -> None:
    assert client.get("/v1/conformance/cr_nope_1").status_code == 404


def _seeded_policy_rule_ids() -> set[str]:
    return {
        str(rule["rule_id"])
        for registry in (
            BASIN_CONTEXT_RULES,
            BASIN_RULES,
            CO_RULES,
            FRACFOCUS_RULES,
            LAND_RULES,
            MT_RULES,
            ND_RULES,
            NM_RULES,
            NM_WELLS_GIS_RULES,
            NM_WELLS_RULES,
            PRODUCING_RULES,
            SCHEDULE_RULES,
            STATUS_HISTORY_RULES,
            TX_RULES,
            ALLOCATION_RULES,
            TYPECURVE_RULES,
            VINTAGE_RULES,
        )
        for rule in registry
        if rule.get("rule_kind") == "code_ref"
    }


def test_the_policy_declarations_are_visible_as_such(client: TestClient) -> None:
    """The code_ref rows are registry data with no executor; they are not hidden. The
    expectation derives from the seed registries, so a new policy declaration changes seeding
    and serving as one act (gate-m17 R-4); the one deliberate membership pin is POLICY_RULES
    in tests/integration/test_seed_rules.py. The floor keeps the derivation non-vacuous."""
    # Explicitly past the default page: the policy set is a whole-registry claim, and the
    # fifth jurisdiction's rules pushed the tail of it onto a second page.
    data = client.get(
        "/v1/conformance", params={"kind": "code_ref", "limit": 200}
    ).json()["data"]

    expected = _seeded_policy_rule_ids()
    assert {
        "cr_nd_liquids_policy_1",
        "cr_nd_well_type_disposal_1",
        "cr_nm_wcproduction_host_pin_1",
        "cr_tx_allocation_scope_1",
    } <= expected
    assert {item["rule_id"] for item in data} == expected


def _publish_rule(
    connection: psycopg.Connection,
    *,
    rule_id: str,
    published_vintage: date,
    effective_from: date = date(2020, 1, 1),
    supersedes_rule_id: str | None = None,
    evidence: tuple[str, str] | None = ("contract-fixture", "a" * 40),
) -> None:
    with connection.cursor() as cursor:
        if evidence is not None:
            cursor.execute(
                "insert into lineage.conformance_rule_publications"
                " (rule_id, published_vintage, evidence_tag, evidence_commit)"
                " values (%s, %s, %s, %s)",
                (rule_id, published_vintage, *evidence),
            )
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, supersedes_rule_id,"
            " source_id, stage, rule_kind, rule, rationale, evidence_url, effective_from)"
            " values (%s, %s, %s, 'nd_mpr_xlsx', 'conform', 'code_ref', %s, %s, %s, %s)",
            (
                rule_id,
                rule_id.rsplit("_", 1)[0],
                supersedes_rule_id,
                f"Rule {rule_id}.",
                "Temporal contract fixture.",
                "https://example.invalid/evidence",
                effective_from,
            ),
        )
    connection.commit()


def test_list_and_detail_do_not_leak_a_future_published_rule(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    _publish_rule(
        seeded,
        rule_id="cr_contract_future_1",
        published_vintage=date(2026, 9, 1),
    )

    before = client.get(
        "/v1/conformance",
        params={"as_of": "2026-08-31", "valid_at": "2026-09-01", "limit": 200},
    ).json()["data"]
    detail_before = client.get(
        "/v1/conformance/cr_contract_future_1",
        params={"as_of": "2026-08-31", "valid_at": "2026-09-01"},
    )
    detail_at = client.get(
        "/v1/conformance/cr_contract_future_1",
        params={"as_of": "2026-09-01", "valid_at": "2026-09-01"},
    )

    assert "cr_contract_future_1" not in {item["rule_id"] for item in before}
    assert detail_before.status_code == 404
    assert detail_at.status_code == 200
    assert detail_at.json()["data"]["published_vintage"] == "2026-09-01"


def test_api_supersession_waits_for_knowledge_and_valid_time(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    _publish_rule(
        seeded,
        rule_id="cr_contract_clock_1",
        published_vintage=date(2026, 8, 1),
    )
    _publish_rule(
        seeded,
        rule_id="cr_contract_clock_2",
        published_vintage=date(2026, 9, 1),
        effective_from=date(2026, 5, 1),
        supersedes_rule_id="cr_contract_clock_1",
    )

    before_publication = client.get(
        "/v1/conformance",
        params={
            "family": "cr_contract_clock",
            "as_of": "2026-08-31",
            "valid_at": "2026-10-01",
        },
    ).json()["data"]
    before_validity = client.get(
        "/v1/conformance",
        params={
            "family": "cr_contract_clock",
            "as_of": "2026-09-01",
            "valid_at": "2026-04-30",
        },
    ).json()["data"]
    fully_eligible = client.get(
        "/v1/conformance",
        params={
            "family": "cr_contract_clock",
            "as_of": "2026-09-01",
            "valid_at": "2026-05-01",
        },
    ).json()["data"]

    assert [item["rule_id"] for item in before_publication] == ["cr_contract_clock_1"]
    assert [item["rule_id"] for item in before_validity] == ["cr_contract_clock_1"]
    assert [item["rule_id"] for item in fully_eligible] == ["cr_contract_clock_2"]


def test_default_reads_known_version_history_without_resolving_valid_time(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    _publish_rule(
        seeded,
        rule_id="cr_contract_history_1",
        published_vintage=date(2020, 1, 1),
        effective_from=date(2010, 1, 1),
    )
    _publish_rule(
        seeded,
        rule_id="cr_contract_history_2",
        published_vintage=date(2020, 1, 2),
        effective_from=date(2020, 1, 1),
        supersedes_rule_id="cr_contract_history_1",
    )

    history = client.get(
        "/v1/conformance", params={"family": "cr_contract_history"}
    ).json()["data"]
    current = client.get(
        "/v1/conformance",
        params={"family": "cr_contract_history", "valid_at": "2026-08-28"},
    ).json()["data"]

    assert [item["rule_id"] for item in history] == [
        "cr_contract_history_2",
        "cr_contract_history_1",
    ]
    assert [item["rule_id"] for item in current] == ["cr_contract_history_2"]
    assert client.get("/v1/conformance/cr_contract_history_1").status_code == 200
    assert (
        client.get(
            "/v1/conformance/cr_contract_history_1",
            params={"valid_at": "2026-08-28"},
        ).status_code
        == 404
    )


def test_cursor_pins_default_knowledge_clock_without_inventing_valid_time(
    client: TestClient,
) -> None:
    response = client.get("/v1/conformance", params={"limit": 1})
    body = response.json()
    cursor = body["meta"]["next_cursor"]
    fingerprint = query_fingerprint(
        {
            "source_id": None,
            "kind": None,
            "family": None,
            "stage": None,
            "field": None,
            "as_of": None,
            "valid_at": None,
        }
    )
    decoded = decode_cursor(cursor, fingerprint=fingerprint)

    assert decoded.as_of == body["meta"]["as_of"]["resolved"] == today().isoformat()
    assert decoded.valid_as_of is None
    assert client.get(body["links"]["next"]).status_code == 200
    assert (
        client.get(
            "/v1/conformance",
            params={"limit": 1, "cursor": cursor, "valid_at": "2026-08-27"},
        ).status_code
        == 422
    )


def test_cursor_pins_explicit_valid_time_independently(client: TestClient) -> None:
    valid_at = "2026-08-27"
    response = client.get(
        "/v1/conformance", params={"limit": 1, "valid_at": valid_at}
    )
    body = response.json()
    fingerprint = query_fingerprint(
        {
            "source_id": None,
            "kind": None,
            "family": None,
            "stage": None,
            "field": None,
            "as_of": None,
            "valid_at": date.fromisoformat(valid_at),
        }
    )
    decoded = decode_cursor(body["meta"]["next_cursor"], fingerprint=fingerprint)

    assert decoded.as_of == today().isoformat()
    assert decoded.valid_as_of == valid_at
    assert client.get(body["links"]["next"]).status_code == 200


def test_applied_by_honors_the_knowledge_cut(
    client: TestClient, seeded: psycopg.Connection
) -> None:
    future_id = "drv_contract_future_conformance"
    with seeded.cursor() as cursor:
        cursor.execute(
            "insert into lineage.derivations"
            " select (jsonb_populate_record(null::lineage.derivations, to_jsonb(d) ||"
            " jsonb_build_object('derivation_id', %s::text, 'created_vintage', '2020-01-01',"
            " 'created_at', '2026-09-01T05:00:00+00:00',"
            " 'correlation_id', 'run_contract_future_conformance'))).*"
            " from lineage.derivations d where derivation_id = %s",
            (future_id, EXAMPLE_DERIVATION_ID),
        )
        cursor.execute(
            "insert into lineage.derivation_rules (derivation_id, rule_id, applied_rows)"
            " values (%s, %s, 1)",
            (future_id, EXAMPLE_RULE_ID),
        )
    seeded.commit()

    before = client.get(
        f"/v1/conformance/{EXAMPLE_RULE_ID}",
        params={"include": "applied_by", "as_of": "2026-08-28"},
    ).json()["data"]["applied_by"]
    after = client.get(
        f"/v1/conformance/{EXAMPLE_RULE_ID}",
        params={"include": "applied_by", "as_of": "2026-09-01"},
    ).json()["data"]["applied_by"]

    assert future_id not in {item["derivation_id"] for item in before}
    assert future_id in {item["derivation_id"] for item in after}


def test_the_evidence_fields_describe_both_states_a_served_pair_can_be_in(
    client: TestClient,
) -> None:
    """The description is the contract a reader has. One that says only "as checked against
    git history" is false for a row the train has not repointed yet."""
    detail = client.app.openapi()["components"]["schemas"]["ConformanceRuleDetail"]
    descriptions = {
        name: detail["properties"][name]["description"]
        for name in ("evidence_tag", "evidence_commit")
    }

    for name, description in descriptions.items():
        assert PLACEHOLDER_TAG in description, f"{name}: the unrepointed state is not described"
    assert "forty zeros" in descriptions["evidence_commit"]


def test_openapi_exposes_both_clocks_and_rule_publication(client: TestClient) -> None:
    document = client.app.openapi()
    collection_parameters = {
        item["name"] for item in document["paths"]["/v1/conformance"]["get"]["parameters"]
    }
    detail_parameters = {
        item["name"]
        for item in document["paths"]["/v1/conformance/{rule_id}"]["get"]["parameters"]
    }
    conformance_schemas = [
        schema
        for name, schema in document["components"]["schemas"].items()
        if name.startswith("ConformanceRule") and "properties" in schema
    ]

    assert {"as_of", "valid_at"} <= collection_parameters
    assert {"as_of", "valid_at"} <= detail_parameters
    assert conformance_schemas
    assert all("published_vintage" in schema["properties"] for schema in conformance_schemas)
