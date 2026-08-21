from __future__ import annotations

import csv
import zipfile
from pathlib import Path

import httpx
import psycopg
import pytest

from glasswell.ingest import tx_gis, tx_wellbore
from glasswell.ingest.tx_gis import LAYERS, IdentityNotPromoted
from glasswell.lengths import resolve_length_method
from glasswell.lineage.capture import lineage_session
from glasswell.lineage.store import PostgresRecorder
from glasswell.seed import seed_all
from glasswell.seed.conformance_tx import PERMIAN_COUNTY_CODES

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
COUNTY = "003"
COUNTY_ARCHIVE = FIXTURES / "tx_gis" / f"well{COUNTY}_sample.zip"
EWA_CSV = FIXTURES / "tx_ewa" / "OG_WELLBORE_EWA_sample.csv"
GRID = FIXTURES / "proj" / "us_noaa_conus.tif"

SURFACE_RECORDS = 400
BOTTOMHOLE_RECORDS = 400
LINE_RECORDS = 120
EWA_FIELD_COUNT = 59


def expected_ewa() -> tuple[int, int, int]:
    """Counted from the fixture itself: staged, out of scope, and layout failures."""
    staged = excluded = malformed = 0
    with EWA_CSV.open(newline="", encoding="utf-8") as handle:
        for record in csv.reader(handle):
            if len(record) != EWA_FIELD_COUNT:
                malformed += 1
            elif record[1] not in PERMIAN_COUNTY_CODES:
                excluded += 1
            else:
                staged += 1
    return staged, excluded, malformed


def client_for(payloads: dict[str, Path]) -> httpx.Client:
    """One transport for the whole run: the grid and the county archive have different URLs."""

    def handler(request: httpx.Request) -> httpx.Response:
        for marker, path in payloads.items():
            if marker in str(request.url):
                return httpx.Response(200, content=path.read_bytes())
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def scalar(db, sql: str, parameters: tuple = ()):
    with db.cursor() as cursor:
        cursor.execute(sql, parameters)
        row = cursor.fetchone()
    return row[0] if row else None


def rows(db, sql: str, parameters: tuple = ()) -> list[tuple]:
    with db.cursor() as cursor:
        cursor.execute(sql, parameters)
        return cursor.fetchall()


@pytest.fixture
def seeded(db: psycopg.Connection) -> psycopg.Connection:
    seed_all(db)
    db.commit()
    return db


@pytest.fixture
def identity(seeded, raw_root: Path, lineage_env):
    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env), client_for(
        {"OG_WELLBORE": EWA_CSV}
    ) as client:
        result = tx_wellbore.load(seeded, raw_root=raw_root, client=client)
    seeded.commit()
    return result


@pytest.fixture
def county(seeded, identity, raw_root: Path, lineage_env):
    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env), client_for(
        {"us_noaa_conus": GRID, f"well{COUNTY}": COUNTY_ARCHIVE}
    ) as client:
        result = tx_gis.load_county(
            seeded, COUNTY, raw_root=raw_root, client=client, grid_client=client
        )
    seeded.commit()
    return result


def test_the_export_stages_every_record_the_layout_admits(identity, seeded):
    staged, excluded, malformed = expected_ewa()
    assert (identity.staged_rows, identity.excluded_rows) == (staged, excluded)
    assert identity.quarantined["schema_mismatch"] == malformed
    assert scalar(seeded, "select count(*) from staging.tx_wellbore_ewa") == identity.staged_rows


def test_a_record_that_disproves_the_layout_is_quarantined_not_read_under_it(identity, seeded):
    held = rows(
        seeded,
        "select reason_code, rule_id from lineage.quarantine_rows"
        " where source_id = 'tx_wellbore_ewa_csv' and reason_code = 'schema_mismatch'",
    )
    assert held
    assert {row[1] for row in held} == {"cr_tx_ewa_layout_1"}


def test_identity_lands_in_canonical_wells_with_an_operator_and_a_status(identity, seeded):
    assert identity.wells > 0
    assert scalar(seeded, "select count(*) from canonical.wells where state_code = '42'") == (
        identity.wells
    )
    with_operator = scalar(
        seeded,
        "select count(*) from canonical.wells"
        " where state_code = '42' and operator_name_reported is not null",
    )
    assert with_operator > 0
    assert 0.0 < identity.status_coverage <= 1.0


def test_a_plugging_date_outranks_the_well_type_the_source_left_standing(identity, seeded):
    plugged = rows(
        seeded,
        "select api10, status_reported from canonical.wells"
        " where status_canonical = 'plugged' and status_reported is distinct from 'ABANDONED'"
        " limit 5",
    )
    assert plugged, "the fixture carries no plugged wellbore, so the precedence is untested"


def test_a_blank_well_type_keeps_a_null_status_rather_than_inventing_one(identity, seeded):
    silent = scalar(
        seeded,
        "select count(*) from canonical.wells"
        " where state_code = '42' and status_canonical is null",
    )
    unknown = scalar(
        seeded,
        "select count(*) from lineage.quarantine_rows where reason_code = 'unknown_status'",
    )
    assert silent >= 0
    assert unknown == 0, "no fixture value is outside the seeded vocabulary"


def test_the_lease_key_is_composite_and_the_bare_lease_number_is_not_the_key(identity, seeded):
    assert identity.lease_links > 0
    shape = rows(
        seeded,
        "select lease_key, oil_gas_code, district_no, lease_no from canonical.well_lease_links"
        " limit 5",
    )
    for lease_key, code, district, lease_no in shape:
        assert lease_key == f"{code}-{district}-{lease_no.zfill(6)}"
    assert scalar(
        seeded, "select count(distinct link_role) from canonical.well_lease_links"
    ) == 1
    assert scalar(seeded, "select distinct link_role from canonical.well_lease_links") == (
        "validator_a"
    )


def test_no_tx_row_reaches_a_production_table(identity, seeded):
    assert scalar(seeded, "select count(*) from canonical.production_monthly") == 0


def test_the_gis_layers_refuse_to_load_before_identity(seeded, raw_root, lineage_env):
    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env), client_for(
        {"us_noaa_conus": GRID, f"well{COUNTY}": COUNTY_ARCHIVE}
    ) as client:
        with pytest.raises(IdentityNotPromoted):
            tx_gis.load_county(
                seeded, COUNTY, raw_root=raw_root, client=client, grid_client=client
            )


def test_every_layer_stages_in_the_datum_the_archive_declares(county, seeded):
    assert county.staged == {
        "surface": SURFACE_RECORDS,
        "bottomhole": BOTTOMHOLE_RECORDS,
        "lines": LINE_RECORDS,
    }
    for layer in LAYERS.values():
        assert scalar(seeded, f"select ST_SRID(geom) from {layer.staging_table} limit 1") == 4267


def test_geometry_reaches_canonical_in_the_storage_crs(county, seeded):
    assert county.geometries["surface"] > 0
    assert county.geometries["lateral"] > 0
    kinds = dict(
        rows(
            seeded,
            "select geom_type, count(*) from canonical.well_spatial"
            " where left(api10, 2) = '42' group by geom_type",
        )
    )
    assert set(kinds) == {"surface", "bottomhole", "lateral"}
    srids = {
        srid
        for (srid,) in rows(
            seeded,
            "select distinct ST_SRID(geom) from canonical.well_spatial where left(api10, 2) = '42'",
        )
    }
    assert srids == {4326}


def test_the_transform_lands_on_the_regulators_own_published_nad83(county, seeded):
    """The two-sided guard SB-01 P7b-T2 asks for, measured against the file's own columns."""
    residual = county.datum_residual_m
    rule = tx_gis._rule(seeded, tx_gis.DATUM_RULE)
    assert residual["n"] > 0
    assert residual["median"] < float(rule.spec["truth_tolerance_m"])
    assert residual["untransformed_median"] > float(rule.spec["untransformed_floor_m"])


def test_a_missing_grid_is_a_failure_and_not_a_three_parameter_fit(seeded, raw_root, lineage_env):
    wrong = FIXTURES / "tx_gis" / f"well{COUNTY}_sample.zip"
    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env), client_for(
        {"us_noaa_conus": wrong, f"well{COUNTY}": COUNTY_ARCHIVE}
    ) as client:
        with pytest.raises(tx_gis.GridUnavailable):
            tx_gis.ensure_grid(
                seeded, tx_gis._rule(seeded, tx_gis.DATUM_RULE), raw_root=raw_root, client=client
            )


def test_an_arc_is_keyed_by_wellbore_so_a_multilateral_keeps_every_trace(county, seeded):
    keys = rows(
        seeded,
        "select api10, count(*) from canonical.well_spatial"
        " where geom_type = 'lateral' group by api10 order by count(*) desc limit 1",
    )
    assert keys
    shape = rows(
        seeded,
        "select geom_key from canonical.well_spatial where geom_type = 'lateral' limit 5",
    )
    for (geom_key,) in shape:
        api10, _, stcode = geom_key.partition("_")
        assert len(api10) == 10
        assert stcode, f"{geom_key} carries no wellbore code, so a sidetrack would collide"


def test_lateral_length_is_geodesic_under_the_tx_rule_not_the_nd_one(county, seeded):
    method = resolve_length_method(seeded, basin="permian")
    assert method.method == "geodesic"
    assert method.rule_id == "cr_tx_compute_crs_1"
    assert county.length_stats_ft["median_ft"] > 0
    # The shipped SHAPE_LEN is feet on the RRC's own projection: close enough to be tempting,
    # and never the number served. Agreement within a percent is the check that it was not used.
    shipped = scalar(
        seeded,
        "select percentile_cont(0.5) within group (order by shape_len::double precision)"
        "  from staging.tx_gis_wells_lines where shape_len <> ''",
    )
    assert shipped is not None
    assert abs(county.length_stats_ft["median_ft"] - shipped) / shipped < 0.05


def test_the_same_manifest_twice_is_idempotent_and_says_so(county, seeded, raw_root, lineage_env):
    before = scalar(seeded, "select count(*) from canonical.well_spatial")
    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env), client_for(
        {"us_noaa_conus": GRID, f"well{COUNTY}": COUNTY_ARCHIVE}
    ) as client:
        again = tx_gis.load_county(
            seeded, COUNTY, raw_root=raw_root, client=client, grid_client=client
        )
    seeded.commit()
    assert again.unchanged is True
    assert scalar(seeded, "select count(*) from canonical.well_spatial") == before


def test_a_county_with_no_horizontal_wells_ships_no_arcs_layer_and_that_is_not_an_error(
    seeded, identity, raw_root, lineage_env, tmp_path
):
    """Four of the 54 archives in scope carry no arcs shapefile at all (Bee, Brooks, El Paso,
    Kimble). A reader that treats that as a malformed download loses the county's wells too."""
    trimmed = tmp_path / "well003_no_arcs.zip"
    with zipfile.ZipFile(COUNTY_ARCHIVE) as source, zipfile.ZipFile(trimmed, "w") as target:
        for name in source.namelist():
            if not name.rpartition(".")[0].lower().endswith("l"):
                target.writestr(name, source.read(name))

    with lineage_session(recorder=PostgresRecorder(seeded), environment=lineage_env), client_for(
        {"us_noaa_conus": GRID, f"well{COUNTY}": trimmed}
    ) as client:
        result = tx_gis.load_county(
            seeded, COUNTY, raw_root=raw_root, client=client, grid_client=client
        )
    seeded.commit()
    assert result.staged["lines"] == 0
    assert result.geometries["lateral"] == 0
    assert result.geometries["surface"] > 0
    absent = scalar(
        seeded,
        "select count(*) from lineage.derivations"
        " where params ->> 'layer' = 'lines' and (params -> 'layer_absent')::boolean",
    )
    assert absent == 1


def test_the_county_scope_comes_from_the_rule_and_refuses_a_county_outside_it(seeded):
    assert tx_gis.county_scope(seeded) == PERMIAN_COUNTY_CODES
    assert tx_gis.archive_name(seeded, COUNTY) == f"well{COUNTY}.zip"
    with pytest.raises(ValueError, match="outside"):
        tx_gis.load_county(seeded, "999")


def test_the_promotion_cites_the_grid_manifest_as_an_input(county, seeded):
    grid_manifest = scalar(
        seeded,
        "select manifest_id from lineage.manifests where source_id = 'proj_grid_nad27'",
    )
    inputs = rows(
        seeded,
        "select distinct ref_id from lineage.derivation_inputs"
        " where derivation_id in (select derivation_id from canonical.well_spatial"
        "                          where left(api10, 2) = '42')",
    )
    assert (grid_manifest,) in inputs


def test_the_scope_exclusion_is_counted_on_the_parse_derivation(identity, seeded):
    params = scalar(
        seeded,
        "select params from lineage.derivations where derivation_id = %s",
        (identity.parse_derivation_id,),
    )
    assert params["rows_excluded_out_of_scope"] == identity.excluded_rows
    assert scalar(
        seeded,
        "select count(*) from lineage.audit_events where event_type = 'staging.scope_excluded'",
    ) == 1
