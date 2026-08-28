from __future__ import annotations

from datetime import date

import pytest

from glasswell.lineage.capture import derive, lineage_session
from glasswell.lineage.errors import LineageUnresolved
from glasswell.lineage.explain import resolve_chain, resolve_chains, to_json
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.store import PostgresRecorder
from tests.support.seed import seed_manifest

VINTAGE = date(2026, 8, 1)


def promote_from_manifest(db, lineage_env) -> tuple[str, str]:
    """A real three-node chain: promote ← parse ← manifest."""
    manifest_id = seed_manifest(db, sha256="a" * 64)
    with lineage_session(
        recorder=PostgresRecorder(db), environment=lineage_env, correlation_id="run_explain"
    ):
        with derive(
            "canonical.promote",
            output=OutputSpec(
                store="postgres",
                dataset="canonical.production_monthly",
                partition={"production_month": "2024-03"},
            ),
            params={"month_convention": "production_month"},
            rules=("cr_nd_units_1",),
        ) as promote:
            with derive(
                "stage.parse",
                output=OutputSpec(store="postgres", dataset="staging.nd_mpr_oil"),
                params={"sheet": "Oil"},
                inputs=[
                    InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=VINTAGE)
                ],
            ) as parse:
                parse.set_output_hash("b" * 64)
            promote.set_output_hash("c" * 64)
    with db.cursor() as cursor:
        cursor.execute(
            "insert into canonical.production_monthly"
            " (api10, production_month, stream, source_id, report_vintage, volume, unit,"
            " days_produced, granularity, value_hash, source_manifest_id, derivation_id)"
            " values ('3305301234', '2024-03-01', 'oil', 'nd_mpr_xlsx', %s, 1, 'bbl', 31,"
            " 'well_observed', %s, %s, %s)",
            (VINTAGE, "d" * 64, manifest_id, promote.derivation_id),
        )
    return promote.derivation_id, manifest_id


def test_a_chain_walks_from_a_served_handle_to_the_terminal_manifest(db, lineage_env):
    root, manifest_id = promote_from_manifest(db, lineage_env)
    chain = resolve_chain(db, f"{root}#api10=3305301234&col=oil_bbl", depth="full")

    assert chain.root == root
    assert [node.type for node in chain.nodes] == ["derivation", "derivation", "manifest"]
    assert chain.terminals == [manifest_id]
    assert chain.truncated is False
    assert chain.as_of_vintage == VINTAGE


def test_the_chain_carries_the_rule_ids_the_promotion_cited(db, lineage_env):
    root, _ = promote_from_manifest(db, lineage_env)
    document = to_json(resolve_chain(db, root, depth="full"))
    assert document["nodes"][0]["conformance_rules"] == [
        {"rule_id": "cr_nd_units_1", "family": None, "kind": None}
    ]
    assert "cr_nd_units_1" in document["nodes"][0]["explanation"]


def test_a_shallow_depth_reports_itself_as_truncated(db, lineage_env):
    root, _ = promote_from_manifest(db, lineage_env)
    chain = resolve_chain(db, root, depth=1)
    assert chain.depth == 1
    assert chain.truncated is True
    assert chain.terminals == []


def test_an_unknown_derivation_raises_lineage_unresolved(db, lineage_env):
    with pytest.raises(LineageUnresolved) as caught:
        resolve_chain(db, "drv_nothinghere")
    assert caught.value.reason == "unknown_id"


def test_the_explain_endpoint_path_caps_the_handle_count(db, lineage_env):
    root, _ = promote_from_manifest(db, lineage_env)
    assert len(resolve_chains(db, [root, root], depth=1)) == 2
    with pytest.raises(ValueError, match="20 handles"):
        resolve_chains(db, [root] * 21)
