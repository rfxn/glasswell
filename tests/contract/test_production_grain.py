"""Production grain as a registry fact: Montana's summed figure, and the window that lied.

Two things this file holds. Montana's promotion has summed across pools since it landed and
said so on the row, but the registry recorded no `production_grain` decision, so the serving
path -- which gates the breakdown link, the rule link and the aggregation warning on that
decision -- served a sum with nothing beside it. And `_pool_grain_warning` asked a windowed
question and a whole-well one and treated the answers as the same fact, so a narrow window told
a well with hundreds of well-grain rows that its regulator files per completion pool and
glasswell performs no rollup.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from glasswell.seed.conformance_mt import MT_RULES
from tests.support.seed import seed_manifest, seed_production, seed_well

pytestmark = pytest.mark.contract

MT_RULE = "cr_mt_bogc_pool_rollup_1"
# One of the 378 servable API-10s' shape: a month it filed in two pools and a month it filed in
# one. A well drawn from the 361 that carry both kinds is not a valid negative, which is what
# makes the negative below a well from the 19,632 that never sum.
SUMMED = "2508388001"
NEVER_SUMS = "2508388002"
# North Dakota, which has registered a grain rule since v0.76: the false sentence reproduces
# there today, and Montana's registration is what would have extended it to 378 more wells.
ND_WELL = "3300788001"
MONTHS = (date(2026, 1, 1), date(2026, 2, 1))
VINTAGE = date(2026, 8, 14)


def rule() -> dict[str, Any]:
    return next(item for item in MT_RULES if item["rule_id"] == MT_RULE)


@pytest.fixture
def grained(seeded: psycopg.Connection) -> psycopg.Connection:
    """Three wells: a Montana one that sums, a Montana one that never does, and a Dakota one
    whose well-grain series is real and whose pool rows are what the window guard is about."""
    manifest = seed_manifest(seeded, sha256="a5" * 32, source_id="mt_bogc_well_production")
    nd_manifest = seed_manifest(seeded, sha256="a6" * 32, source_id="nd_mpr_xlsx")
    for api10, state, filed in ((SUMMED, "25", "Producing"), (NEVER_SUMS, "25", "Producing")):
        seed_well(
            seeded,
            api10=api10,
            state_code=state,
            status_reported=filed,
            status_canonical="active",
            manifest_id=manifest,
        )
    seed_well(seeded, api10=ND_WELL, state_code="33", manifest_id=nd_manifest)

    for month in MONTHS:
        summed = month == MONTHS[0]
        for pool in range(2 if summed else 1):
            seed_production(
                seeded,
                api10=SUMMED,
                production_month=month,
                report_vintage=VINTAGE,
                volume=Decimal("400"),
                source_id="mt_bogc_well_production",
                entity_type="well_completion_pool",
                entity_key=f"{SUMMED}:BAKKEN{pool}",
                reporting_level="well_completion_pool",
                well_completion_pool=f"BAKKEN{pool}",
                manifest_id=manifest,
                derivation_id=_derivation(seeded),
            )
        seed_production(
            seeded,
            api10=SUMMED,
            production_month=month,
            report_vintage=VINTAGE,
            volume=Decimal("800") if summed else Decimal("400"),
            source_id="mt_bogc_well_production",
            entity_type="well",
            entity_key=SUMMED,
            reporting_level="well_completion_pool" if summed else "well",
            aggregation="sum_over_pools" if summed else None,
            manifest_id=manifest,
            derivation_id=_derivation(seeded),
        )
        seed_production(
            seeded,
            api10=NEVER_SUMS,
            production_month=month,
            report_vintage=VINTAGE,
            volume=Decimal("310"),
            source_id="mt_bogc_well_production",
            entity_type="well",
            entity_key=NEVER_SUMS,
            reporting_level="well",
            manifest_id=manifest,
            derivation_id=_derivation(seeded),
        )
        # The Dakota well: a real well-grain series, and pool rows behind it. Both are needed,
        # because the defect is the two being counted over different windows.
        seed_production(
            seeded,
            api10=ND_WELL,
            production_month=month,
            report_vintage=VINTAGE,
            volume=Decimal("250"),
            entity_type="well",
            entity_key=ND_WELL,
            reporting_level="well",
            manifest_id=nd_manifest,
            derivation_id=_derivation(seeded),
        )
        seed_production(
            seeded,
            api10=ND_WELL,
            production_month=month,
            report_vintage=VINTAGE,
            volume=Decimal("250"),
            entity_type="well_completion_pool",
            entity_key=f"{ND_WELL}:BAKKEN",
            reporting_level="well_completion_pool",
            well_completion_pool="BAKKEN",
            manifest_id=nd_manifest,
            derivation_id=_derivation(seeded),
        )
    seeded.commit()
    return seeded


_DERIVATION: dict[int, str] = {}


def _derivation(connection: psycopg.Connection) -> str:
    from tests.support.seed import seed_derivation

    key = id(connection)
    if key not in _DERIVATION:
        _DERIVATION[key] = seed_derivation(connection)
    return _DERIVATION[key]


def production(client: TestClient, api10: str, **params: Any) -> dict[str, Any]:
    response = client.get(f"/v1/wells/{api10}/production", params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    return {**body["data"], "meta": body["meta"], "links": body["links"]}


def test_a_montana_well_that_sums_names_the_rule_that_says_so(
    client: TestClient, grained: psycopg.Connection
) -> None:
    """DR-WC1 (a). No code changes for this: production.py already reads the registry, so the
    row is the whole of the fix and the three surfaces start answering together."""
    body = production(client, SUMMED)

    assert body["links"]["pools"] == f"/v1/wells/{SUMMED}/production/pools"
    assert body["links"]["aggregation_rule"] == f"/v1/conformance/{MT_RULE}"
    warnings = {item["code"]: item["detail"] for item in body["meta"]["warnings"]}
    assert MT_RULE in warnings["pools_aggregated"]
    assert client.get(f"/v1/conformance/{MT_RULE}").status_code == 200


def test_a_montana_well_that_never_sums_is_told_none_of_it(
    client: TestClient, grained: psycopg.Connection
) -> None:
    """The negative is drawn from the 19,632 that never sum, not from the 361 that carry both
    kinds: a well of that second shape is summed in one window and not in the next, so it would
    prove whichever answer the window happened to give."""
    body = production(client, NEVER_SUMS)

    assert "pools" not in body["links"]
    assert "aggregation_rule" not in body["links"]
    assert [item["code"] for item in body["meta"]["warnings"]] == []


def test_the_emission_is_per_response_window_because_the_attribute_is_per_row(
    client: TestClient, grained: psycopg.Connection
) -> None:
    """Aggregation is a per-row attribute. The well that summed in January did not in February,
    and the response says which months were summed rather than labelling the well."""
    summed_month = production(client, SUMMED, **{"from": "2026-01", "to": "2026-01"})
    plain_month = production(client, SUMMED, **{"from": "2026-02", "to": "2026-02"})

    assert "pools_aggregated" in {item["code"] for item in summed_month["meta"]["warnings"]}
    assert "pools_aggregated" not in {item["code"] for item in plain_month["meta"]["warnings"]}


def test_the_rule_states_the_four_numbers_and_says_the_attribute_is_per_row(
    client: TestClient, grained: psycopg.Connection
) -> None:
    """M-8: 389 + 19,993 was never 20,021, and a false number inside a published rationale is
    the failure class this whole track exists to close."""
    spec = rule()["spec"]
    rationale = str(rule()["rationale"])

    assert spec["api10_with_well_grain_rows"] == 20021
    assert spec["api10_with_any_summed_row"] == 389
    assert spec["api10_summed_only"] == 28
    assert spec["api10_summed_and_unsummed"] == 361
    assert spec["api10_never_summed"] == 19632
    assert 28 + 361 == 389
    assert "per-row attribute" in rationale
    assert "378 are servable" in rationale


def test_a_narrow_window_no_longer_says_no_rollup_is_performed_over_a_well_that_has_one(
    client: TestClient, grained: psycopg.Connection
) -> None:
    """N-10, the defect this track extends rather than introduces.

    `observed` is windowed and the pool-row count is not, so any window a well filed nothing in
    emptied one while the other stayed positive. Reproduced on the deployed instance against
    3300700014, which has 408 well-grain rows and none in 1975, and which was told under
    `?from=1975-01&to=1975-12` that its regulator files per completion pool and glasswell
    performs no rollup. Registering Montana's rule would have made 378 more wells eligible for
    the same false sentence, so the phase that makes them eligible closes it.
    """
    narrow = production(client, ND_WELL, **{"from": "1975-01", "to": "1975-12"})

    assert narrow["series"]["pm"] == []
    assert "production_reported_at_pool_grain" not in {
        item["code"] for item in narrow["meta"]["warnings"]
    }


POOL_ONLY = "3300788002"


def test_a_well_with_no_well_grain_series_at_all_still_gets_the_panel(
    client: TestClient, grained: psycopg.Connection
) -> None:
    """The guard narrows the warning to what it was written for and no further: a well whose
    regulator files at pool grain and rolls nothing up to it still says so, over any window.

    A well of its own rather than the Dakota one with its well rows removed: canonical is
    append-only, so "the same well without its series" is not a state this tier can construct
    and is not one the spine can reach either.
    """
    manifest = seed_manifest(grained, sha256="a7" * 32, source_id="nd_mpr_xlsx")
    seed_well(grained, api10=POOL_ONLY, state_code="33", manifest_id=manifest)
    for month in MONTHS:
        seed_production(
            grained,
            api10=POOL_ONLY,
            production_month=month,
            report_vintage=VINTAGE,
            volume=Decimal("180"),
            entity_type="well_completion_pool",
            entity_key=f"{POOL_ONLY}:BAKKEN",
            reporting_level="well_completion_pool",
            well_completion_pool="BAKKEN",
            manifest_id=manifest,
            derivation_id=_derivation(grained),
        )
    grained.commit()

    body = production(client, POOL_ONLY)

    assert body["series"]["pm"] == []
    assert "production_reported_at_pool_grain" in {
        item["code"] for item in body["meta"]["warnings"]
    }
