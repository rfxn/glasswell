"""Every served New Mexico figure carries the rule that shaped it.

Phase 12 makes New Mexico figures servable — the spine is rooted on `canonical.wells`, so the
first prefix-30 header opens the gate for 17.6M production rows already resident. This file is
about what has to be true at that instant: a status vocabulary handle, a geometry provenance
handle, a liquids basis that is New Mexico's and not North Dakota's, and an aggregation rule
that says what New Mexico's pool grain actually means.

The North Dakota and Texas equivalents are asserted in the same file, because a dictionary
lookup that gained a third key is exactly where a regression hides.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from glasswell.api.examples import EXAMPLE_API10
from glasswell.api.routers.production import LIQUIDS_RULES, ROLLUP_RULES
from glasswell.api.routers.wells import PROVENANCE_RULES, STATUS_VOCABULARY_RULES
from tests.contract.conftest import TX_API10
from tests.support.seed import seed_well, seed_well_spatial

NM_API10 = "3001599001"
NM_POOL = "96269"
NM_SURFACE = "POINT(-103.9000 32.1000)"
NM_MONTHS = (date(2026, 5, 1), date(2026, 6, 1))
NM_VINTAGE = date(2026, 8, 20)


@pytest.fixture
def with_new_mexico(seeded: psycopg.Connection, client: TestClient) -> TestClient:
    """One New Mexico well beside the fixture's North Dakota and Texas ones.

    Its production is filed at pool grain and nothing rolls it up, which is the live shape:
    17,597,960 rows, every one well_completion_pool, not one entity_type = well among them.
    """
    with seeded.cursor() as cursor:
        cursor.execute(
            "select source_manifest_id, derivation_id from canonical.production_monthly limit 1"
        )
        manifest_id, derivation_id = cursor.fetchone()
    seed_well(
        seeded,
        api10=NM_API10,
        state_code="30",
        county_code_at_permit="015",
        ndic_file_no=None,
        basin="permian",
        land_unit_label=None,
        status_canonical=None,
        status_reported="A",
        well_type_reported="O",
        well_name="MEWBOURNE 22 FEDERAL COM 1H",
        operator_name_reported="MEWBOURNE OIL COMPANY",
        manifest_id=manifest_id,
        derivation_id=derivation_id,
    )
    seed_well_spatial(
        seeded,
        api10=NM_API10,
        geom_type="surface",
        wkt=NM_SURFACE,
        manifest_id=manifest_id,
        derivation_id=derivation_id,
    )
    with seeded.cursor() as cursor:
        cursor.executemany(
            "insert into canonical.production_monthly (api10, entity_type, entity_key,"
            " reporting_level, well_completion_pool, production_month, stream, source_id,"
            " report_vintage, volume, unit, granularity, value_hash, null_semantics,"
            " source_manifest_id, derivation_id)"
            " values (%(api10)s, 'well_completion_pool', %(entity_key)s, 'well_completion_pool',"
            " %(pool)s, %(month)s, %(stream)s, 'nm_ocd_wcproduction', %(vintage)s, %(volume)s,"
            " %(unit)s, 'well_observed', %(value_hash)s, 'reported', %(manifest_id)s,"
            " %(derivation_id)s)",
            [
                {
                    "api10": NM_API10,
                    "entity_key": f"{NM_API10}:{NM_POOL}",
                    "pool": NM_POOL,
                    "month": month,
                    "stream": stream,
                    "vintage": NM_VINTAGE,
                    "volume": Decimal("101.500"),
                    "unit": unit,
                    "value_hash": "e" * 64,
                    "manifest_id": manifest_id,
                    "derivation_id": derivation_id,
                }
                for month in NM_MONTHS
                for stream, unit in (("oil", "bbl"), ("gas", "mcf"), ("water", "bbl"))
            ],
        )
        cursor.execute(
            "insert into lineage.quarantine_rows (quarantine_id, row_fingerprint, source_id,"
            " staging_table, stage, reason_code, rule_id, row_payload, first_seen_at,"
            " first_seen_manifest_id, last_seen_at, last_seen_manifest_id, occurrence_count,"
            " state) values ('qtn_nm_coord', %s, 'nm_ocd_wellhistory',"
            " 'staging.stg_nm_ocd_wellhistory__records', 'validate', 'coordinate_sentinel',"
            " 'cr_nm_wellhistory_coordinate_1', %s, now(), %s, now(), %s, 4, 'open')",
            ("c" * 64, Jsonb({"api10": "3001599009"}), manifest_id, manifest_id),
        )
    seeded.commit()
    return client


def body(client: TestClient, path: str, **params) -> dict:
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_new_mexico_well_resolves_rather_than_404ing(with_new_mexico: TestClient) -> None:
    """The gate, from the serving side."""
    data = body(with_new_mexico, f"/v1/wells/{NM_API10}")["data"]

    assert data["api10"] == NM_API10
    assert data["state_code"] == "30"


def test_the_status_vocabulary_rule_is_new_mexicos(with_new_mexico: TestClient) -> None:
    summary = body(
        with_new_mexico, "/v1/wells/status-summary", bbox="-104.5,31.5,-103.0,32.8"
    )["data"]
    basins = {row["state_code"]: row for row in summary["basins"]}

    assert basins["30"]["status_vocabulary_rule"] == "cr_nm_wellhistory_status_vocab_1"
    assert "cr_nm_wellhistory_status_vocab_1" in summary["vocabulary_rules"]


def test_no_status_vocabulary_unavailable_warning_is_emitted_for_new_mexico(
    with_new_mexico: TestClient,
) -> None:
    """`wells.py` warns for every state its mapping does not carry; 30 is now carried."""
    envelope = body(with_new_mexico, "/v1/wells/status-summary", bbox="-104.5,31.5,-103.0,32.8")
    codes = {item["code"] for item in envelope["meta"].get("warnings", [])}

    assert "status_vocabulary_unavailable" not in codes


def test_every_pinned_status_rule_resolves_to_a_seeded_row_that_decides_a_vocabulary(
    client: TestClient,
) -> None:
    """Stronger than a kind check: a `vocab_map` must name the table it maps through, and a
    declaration must say in its own spec that no mapping exists. Both are decisions about the
    status vocabulary; only one of them is a mapping."""
    for state_code, rule_id in sorted(STATUS_VOCABULARY_RULES.items()):
        response = client.get(f"/v1/conformance/{rule_id}")
        assert response.status_code == 200, (state_code, rule_id)
        rule = response.json()["data"]

        assert rule["rule_kind"] in {"vocab_map", "parse_directive"}, rule_id
        if rule["rule_kind"] == "vocab_map":
            assert rule["spec"].get("mapping_table"), rule_id
        else:
            assert rule["spec"].get("mapping_table") is None, rule_id
            assert rule["spec"].get("status_canonical") is None, rule_id
            assert rule["spec"].get("measured_domain"), rule_id


def test_the_geometry_provenance_rule_is_new_mexicos(with_new_mexico: TestClient) -> None:
    envelope = body(with_new_mexico, "/v1/wells/status-summary", bbox="-104.5,31.5,-103.0,32.8")

    assert envelope["data"]["geometry_provenance"]
    assert (
        envelope["links"]["cr_nm_wellhistory_geometry_provenance_1"]
        == "/v1/conformance/cr_nm_wellhistory_geometry_provenance_1"
    )
    assert "cr_nd_geometry_provenance_1" not in envelope["links"]


def test_every_pinned_provenance_rule_resolves(client: TestClient) -> None:
    for rule_id in sorted(set(PROVENANCE_RULES.values())):
        assert client.get(f"/v1/conformance/{rule_id}").status_code == 200, rule_id


def test_the_pool_series_cites_new_mexicos_grain_rule_not_north_dakotas(
    with_new_mexico: TestClient,
) -> None:
    envelope = body(with_new_mexico, f"/v1/wells/{NM_API10}/production/pools")

    assert (
        envelope["links"]["aggregation_rule"]
        == "/v1/conformance/cr_nm_wcproduction_pool_rollup_1"
    )
    assert "cr_nd_pool_rollup_1" not in envelope["links"]["aggregation_rule"]


def test_the_liquids_basis_on_a_new_mexico_oil_figure_is_new_mexicos(
    with_new_mexico: TestClient,
) -> None:
    """New Mexico reports condensate as its own stream (cr_nm_wcproduction_liquids_1), so its
    oil is oil as filed. Serving North Dakota's oil+condensate here would be a liquids policy
    with no New Mexico row behind it, on a sidecar `lineage/envelope.py` makes mandatory."""
    data = body(with_new_mexico, f"/v1/wells/{NM_API10}/production/pools")["data"]
    basis = data["_basis"]

    assert set(basis.values()) == {"oil", "water"}
    assert "oil+condensate" not in str(basis)
    assert any(key.endswith("oil_bbl") for key in basis)
    assert data["pools"][0]["series"]["oil_bbl"]


def test_an_empty_well_level_series_says_why_rather_than_reading_as_no_production(
    with_new_mexico: TestClient,
) -> None:
    """New Mexico promotes only pool rows and rolls nothing up, so the well-level series is
    absent, not zero. An empty chart would say the opposite of what is true (DIR-3)."""
    envelope = body(with_new_mexico, f"/v1/wells/{NM_API10}/production")
    warnings = {item["code"]: item for item in envelope["meta"].get("warnings", [])}

    assert "production_reported_at_pool_grain" in warnings
    detail = warnings["production_reported_at_pool_grain"]["detail"]
    assert "cr_nm_wcproduction_pool_rollup_1" in detail
    assert f"/v1/wells/{NM_API10}/production/pools" in detail


def test_a_new_mexico_well_is_producing_unknown_and_the_reason_is_disclosed(
    with_new_mexico: TestClient,
) -> None:
    """`unknown` is the safe value and the wrong story without the reason.

    marts/producing.py evaluates `entity_type = 'well'` and New Mexico has none, so an NM well
    that filed 17.6M pool rows would otherwise be reported under a field whose description
    offers only "filed nothing", "withheld" and "reports at the lease" — none of which is true
    of it.
    """
    envelope = body(with_new_mexico, f"/v1/wells/{NM_API10}")
    warnings = {item["code"]: item for item in envelope["meta"].get("warnings", [])}

    assert envelope["data"]["producing"] == "unknown"
    assert "production_reported_at_pool_grain" in warnings
    disclosure = warnings["production_reported_at_pool_grain"]
    assert "cr_nm_wcproduction_pool_rollup_1" in disclosure["detail"]
    assert disclosure["pointer"] == "/producing"


def test_the_reason_comes_from_the_registry_not_from_a_state_code_in_the_path(
    seeded: psycopg.Connection,
) -> None:
    """Both causes of an absent well-level series resolve from `lineage.conformance_rules`."""
    from glasswell.lineage.conformance import lease_reporting_rule, pool_grain_rule
    from glasswell.marts.producing import no_well_series_states

    assert pool_grain_rule(seeded, "30") is not None
    assert pool_grain_rule(seeded, "33") is None
    # Texas's absence is the lease reason, not this one; the two must not collapse.
    assert pool_grain_rule(seeded, "42") is None
    assert "30" in no_well_series_states(seeded)
    assert "33" not in no_well_series_states(seeded)
    if lease_reporting_rule(seeded, "42") is not None:
        assert "42" in no_well_series_states(seeded)


def test_a_north_dakota_well_carries_no_pool_grain_disclosure(client: TestClient) -> None:
    """The regression half: ND rolls up under cr_nd_pool_rollup_1, so the reason does not apply."""
    envelope = body(client, f"/v1/wells/{EXAMPLE_API10}")
    codes = {item["code"] for item in envelope["meta"].get("warnings", [])}

    assert "production_reported_at_pool_grain" not in codes


def test_the_north_dakota_equivalents_are_unchanged(client: TestClient) -> None:
    """The regression half. A third key in a lookup is where the first two get lost."""
    data = body(client, f"/v1/wells/{EXAMPLE_API10}/production")["data"]

    assert data["_basis"]["series.oil_bbl"] == "oil+condensate"
    assert data["_basis"]["series.water_bbl"] == "water"
    assert STATUS_VOCABULARY_RULES["33"] == "cr_nd_status_vocab_1"
    assert ROLLUP_RULES["33"] == "cr_nd_pool_rollup_1"
    assert LIQUIDS_RULES["33"] == "cr_nd_liquids_policy_1"
    assert PROVENANCE_RULES["33"] == "cr_nd_geometry_provenance_1"


def test_the_texas_equivalents_are_unchanged(client: TestClient) -> None:
    data = body(client, f"/v1/wells/{TX_API10}")["data"]

    assert data["state_code"] == "42"
    assert STATUS_VOCABULARY_RULES["42"] == "cr_tx_status_vocab_1"
    # A pre-existing residual, stated rather than silently inherited: the registry carries no
    # cr_tx_geometry_provenance_1, so Texas cites North Dakota's classing rule as it always has.
    assert PROVENANCE_RULES["42"] == "cr_nd_geometry_provenance_1"
    assert "42" not in ROLLUP_RULES
    assert "42" not in LIQUIDS_RULES


def test_a_state_with_no_registered_policy_gets_no_other_states_policy() -> None:
    """The failure mode this phase exists to close, stated as a property of the resolvers."""
    from glasswell.api.routers.production import rollup_rule, stream_basis

    assert stream_basis("oil", "42") is None
    assert stream_basis("oil", None) is None
    assert stream_basis("water", "42") == "water"
    assert stream_basis("gas", "33") is None
    assert rollup_rule("42") is None
    assert rollup_rule("30") == "cr_nm_wcproduction_pool_rollup_1"


def test_the_new_mexico_quarantine_reason_is_servable_with_its_rule(
    with_new_mexico: TestClient,
) -> None:
    envelope = body(with_new_mexico, "/v1/quarantine", reason_code="coordinate_sentinel")
    rows = envelope["data"]["rows"] if "rows" in envelope["data"] else envelope["data"]

    assert rows
    assert any(
        row.get("rule_id") == "cr_nm_wellhistory_coordinate_1"
        for row in (rows if isinstance(rows, list) else [rows])
    )


def test_explain_resolves_a_new_mexico_figure_to_a_real_derivation(
    with_new_mexico: TestClient,
) -> None:
    envelope = body(with_new_mexico, f"/v1/wells/{NM_API10}/production/pools", explain="true")

    assert envelope["_explain"]
