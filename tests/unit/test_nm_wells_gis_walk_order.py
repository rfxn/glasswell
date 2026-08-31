"""The OCD public wells walk, offline: identity, order and the refusals that stop it.

Nothing here opens a socket. What it pins is the half of the source that a network fault would
otherwise only reveal at 3am inside a fetch: the dashed-id normalisation, the walk order the
registry names, the duplicate tripwire, and the two refusals `arcgis.py` raises — a
non-allowlisted host, and a token gate that halts rather than retrying a sibling.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from glasswell.ingest import nm_wells_gis
from glasswell.ingest.arcgis import (
    ALLOWED_HOSTS,
    HostNotAllowlisted,
    HostTokenGated,
    _require_allowlisted,
    _walk,
)
from glasswell.ingest.nm_wells_gis import api10_from_dashed, parse_features
from glasswell.seed.conformance_nm_wells import NM_WELLS_GIS_RULES
from tests.support.layers import schema_reads_in

pytestmark = pytest.mark.unit


def rule(rule_id: str) -> dict:
    return next(item for item in NM_WELLS_GIS_RULES if item["rule_id"] == rule_id)


def feature(identifier: str, longitude: float = -103.9, latitude: float = 32.1) -> dict:
    properties = dict.fromkeys(nm_wells_gis.COLUMNS, None)
    properties["id"] = identifier
    properties["latitude"] = latitude
    properties["longitude"] = longitude
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
        "properties": properties,
    }


def test_the_dashed_id_normalises_to_the_undashed_api10():
    assert api10_from_dashed("30-001-00505") == "3000100505"


@pytest.mark.parametrize(
    "identifier",
    ["3000100505", "30-01-00505", "30-001-005050", "", None, "30-001-0050A", "30-001-00505-01"],
)
def test_an_id_that_is_not_two_three_five_digits_is_refused_never_repaired(identifier):
    """Stripping non-digits from an API-14 would key a wellbore onto its well; zero-padding a
    short id would build a syntactically perfect API-10 for a well that does not exist."""
    with pytest.raises(ValueError, match="is not a dashed API-10"):
        api10_from_dashed(identifier)


def test_the_walk_is_ordered_by_the_unique_id_and_never_by_objectid():
    spec = rule("cr_nm_wells_gis_walk_order_1")["spec"]

    assert spec["order_by"] == "id ASC"
    assert spec["rejected_order"] == "OBJECTID ASC"
    assert spec["measured_2026_08_30"]["id_is_unique"] is True
    assert (
        spec["measured_2026_08_30"]["features"]
        == spec["measured_2026_08_30"]["distinct_id"]
    )


def test_the_module_walks_in_the_order_the_registry_names():
    """The order is read from the rule at fetch time; the constant here is only the default."""
    assert nm_wells_gis.WALK_ORDER_RULE_ID == "cr_nm_wells_gis_walk_order_1"
    assert "order_by" in rule(nm_wells_gis.WALK_ORDER_RULE_ID)["spec"]


def test_a_repeated_id_inside_one_harvest_is_a_duplicate_row_not_a_second_filing():
    parsed = parse_features(
        enumerate([feature("30-001-00505"), feature("30-001-00505", -103.8, 32.2)]),
        manifest_id="man_x",
    )

    assert len(parsed.rows) == 2, "both rows are staged; staging holds no opinions"
    assert [reject["reason_code"] for reject in parsed.rejects] == ["duplicate_row"]


def test_an_unkeyable_id_is_staged_and_held_beside_itself():
    parsed = parse_features(enumerate([feature("not-an-api")]), manifest_id="man_x")

    assert len(parsed.rows) == 1
    assert [reject["reason_code"] for reject in parsed.rejects] == ["key_incomplete"]


def test_a_feature_with_no_point_is_a_parse_error_rather_than_a_dropped_row():
    broken = feature("30-001-00505")
    broken["geometry"] = None
    parsed = parse_features(enumerate([broken]), manifest_id="man_x")

    assert parsed.rows[0]["geom_wkt"] is None
    assert [reject["reason_code"] for reject in parsed.rejects] == ["parse_error"]


def test_a_property_the_staging_table_declares_and_the_service_drops_is_schema_drift():
    thin = feature("30-001-00505")
    del thin["properties"]["ulstr"]

    with pytest.raises(nm_wells_gis.SchemaDrift):
        parse_features(enumerate([thin]), manifest_id="man_x")


def test_the_service_host_is_already_allowlisted_so_no_amendment_is_required():
    assert "gis.emnrd.nm.gov" in ALLOWED_HOSTS
    assert nm_wells_gis.SERVICE_URL.startswith("https://gis.emnrd.nm.gov/")


def test_a_service_on_a_host_outside_the_allowlist_is_refused():
    """The gate is before the socket, which is the point: an unlisted host is never contacted."""
    with pytest.raises(HostNotAllowlisted):
        _require_allowlisted("https://gis.example.invalid/arcgis/rest/services/X/FeatureServer")
    _require_allowlisted(nm_wells_gis.SERVICE_URL)


@pytest.mark.parametrize("code", [403, 429, 499])
def test_a_token_gate_halts_the_walk_rather_than_retrying_a_sibling(tmp_path: Path, code: int):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(code, json={"error": {"code": code}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HostTokenGated):
            _walk(
                client,
                tmp_path / "payload.geojsonl",
                service_url=nm_wells_gis.SERVICE_URL,
                layer_id=0,
                where="1=1",
                page_size=2,
                page_delay_seconds=0.0,
                order_by="id ASC",
            )
    assert len(calls) == 1, "a halt is a halt: no sibling retry and no fallback mirror"


def test_the_parity_rule_is_a_prohibition_because_the_distribution_is_not_measured():
    """A tolerance band with no distribution behind it is an assertion wearing a
    measurement's clothes. What is measured — the cardinality — is recorded; what is not is
    named as absent, and the rule refuses a preference until it exists."""
    spec = rule("cr_nm_wells_gis_parity_1")["spec"]

    assert spec["form"] == "prohibition"
    assert spec["distance_distribution_measured"] is None
    assert spec["on_disagreement"] == "report both and promote neither"
    assert spec["on_present_in_one_source_only"].startswith("count and report")
    assert spec["cardinality_measured"]["gis_distinct_api10_2026_08_30"] == 141_916
    assert spec["cardinality_measured"]["ftp_distinct_api10_2026_08_20"] == 142_000


def test_no_superseding_header_precedence_row_is_seeded_before_the_measurement():
    """cr_nm_wellhistory_header_precedence_2 is the row this measurement is for, and seeding it
    now would decide a question on evidence that does not exist yet."""
    from glasswell.seed.conformance_nm_wells import NM_WELLS_RULES

    ids = {str(item["rule_id"]) for item in (*NM_WELLS_RULES, *NM_WELLS_GIS_RULES)}

    assert "cr_nm_wellhistory_header_precedence_1" in ids
    assert "cr_nm_wellhistory_header_precedence_2" not in ids


def test_the_source_stops_at_staging_on_purpose():
    assert nm_wells_gis.STAGING_TABLE == "staging.nm_ocd_wells_gis"
    assert rule("cr_nm_wells_gis_source_1")["spec"]["terminus"] == "staging"
    # Read from the parsed module: a substring grep over the file text is satisfied by a name
    # written in pieces, which still executes as a canonical read.
    assert schema_reads_in(Path(nm_wells_gis.__file__), "canonical") == []
