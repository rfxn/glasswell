"""Two independent New Mexico well populations, compared — and the preference not yet taken.

The FTP header archive is frozen at 2026-08-20; the OCD public wells layer is refreshed as
permits are approved. What this file asserts is the shape of the comparison, on a fixture whose
overlap is arranged so every cardinality is a number rather than a coincidence: wells in both,
wells only in the GIS layer, and wells only in the FTP archive.

What it does *not* assert is a tolerance band, because none has been measured. The parity rule
is written as a prohibition for that reason, and this file holds it to that form.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from glasswell.ingest import nm_wells_gis
from glasswell.ingest.base import open_ingest_run
from glasswell.seed import seed_all
from tests.integration.test_nm_stage import stage
from tests.integration.test_nm_stage import staging_root as _staging_root
from tests.support.fakes import FixedClock

staging_root = _staging_root

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parents[1] / "fixtures" / "nm_ocd" / "nm_wellhistory_headers.xml"
DAY_ONE = datetime(2026, 8, 31, 6, 15, 0, tzinfo=UTC)
# One well the GIS layer carries and the header archive does not: a permit approved after the
# archive was sealed is the ordinary case, not an anomaly.
GIS_ONLY = "30-999-99999"


@pytest.fixture
def seeded(db: psycopg.Connection) -> None:
    seed_all(db)
    db.commit()


@pytest.fixture
def ftp_headers(db, seeded, raw_root, staging_root, tmp_path, monkeypatch):
    """The header archive's own bytes, staged: the population the GIS layer is measured against."""
    stage(
        db,
        raw_root,
        tmp_path,
        monkeypatch,
        table="wellhistory",
        document=FIXTURE.read_bytes(),
        at=DAY_ONE,
    )
    with db.cursor() as cursor:
        cursor.execute(
            "select distinct lpad(api_st_cde, 2, '0') || lpad(api_cnty_cde, 3, '0')"
            "     || lpad(api_well_idn, 5, '0')"
            "  from staging.stg_nm_ocd_wellhistory__records order by 1"
        )
        return [api10 for (api10,) in cursor.fetchall()]


def gis_payload(path: Path, api10s: list[str]) -> Path:
    """A geojsonl page per feature, in the walk order the rule names."""
    lines = []
    for index, api10 in enumerate(sorted(api10s)):
        properties = dict.fromkeys(nm_wells_gis.COLUMNS, None)
        properties["id"] = f"{api10[:2]}-{api10[2:5]}-{api10[5:]}" if "-" not in api10 else api10
        properties["ulstr"] = "F-19-11N-04E"
        properties["status"] = "Active"
        longitude, latitude = -103.9 - index * 0.0001, 32.1 + index * 0.0001
        properties["latitude"] = latitude
        properties["longitude"] = longitude
        lines.append(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                            "properties": properties,
                        }
                    ],
                }
            )
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def stage_gis(db, payload: Path, *, manifest_sha: str) -> nm_wells_gis.LoadResult:
    """Stage the fixture payload directly: the walk itself is covered offline, and this file is
    about what the two populations say when compared, not about the transport."""
    from tests.support.seed import seed_manifest

    with open_ingest_run(
        db, source_id=nm_wells_gis.SOURCE_ID, clock=FixedClock(DAY_ONE)
    ) as run:
        manifest_id = seed_manifest(
            run.connection,
            sha256=manifest_sha,
            source_id=nm_wells_gis.SOURCE_ID,
            source_key=nm_wells_gis.SOURCE_KEY,
        )
        result = nm_wells_gis._stage(
            run.connection,
            payload,
            manifest_id=manifest_id,
            vintage=DAY_ONE.date(),
            source_epsg=4269,
            storage_epsg=4326,
        )
    db.commit()
    return result


def parity(db) -> dict[str, int]:
    """The three cardinalities, computed the way the parity rule describes them."""
    with db.cursor() as cursor:
        cursor.execute(
            "with gis as ("
            "  select distinct replace(id, '-', '') as api10 from staging.nm_ocd_wells_gis"
            "   where id ~ '^[0-9]{2}-[0-9]{3}-[0-9]{5}$'),"
            " ftp as ("
            "  select distinct lpad(api_st_cde, 2, '0') || lpad(api_cnty_cde, 3, '0')"
            "       || lpad(api_well_idn, 5, '0') as api10"
            "    from staging.stg_nm_ocd_wellhistory__records)"
            " select (select count(*) from gis join ftp using (api10)),"
            "        (select count(*) from gis where api10 not in (select api10 from ftp)),"
            "        (select count(*) from ftp where api10 not in (select api10 from gis))"
        )
        both, gis_only, ftp_only = cursor.fetchone()
    return {"both": both, "gis_only": gis_only, "ftp_only": ftp_only}


def test_the_three_cardinalities_are_asserted_rather_than_narrated(db, ftp_headers, tmp_path):
    payload = gis_payload(
        tmp_path / "wells.geojsonl", [*ftp_headers[:-1], GIS_ONLY.replace("-", "")]
    )
    stage_gis(db, payload, manifest_sha="a1" * 32)

    counts = parity(db)

    assert counts["both"] == len(ftp_headers) - 1
    assert counts["gis_only"] == 1
    assert counts["ftp_only"] == 1
    assert counts["both"] + counts["ftp_only"] == len(ftp_headers)


def test_a_well_in_one_source_only_is_reported_never_silently_dropped(db, ftp_headers, tmp_path):
    """The count is the parity rule's substrate: a source that quietly drops its non-overlap has
    nothing left to compare."""
    payload = gis_payload(
        tmp_path / "wells.geojsonl", [*ftp_headers[:-1], GIS_ONLY.replace("-", "")]
    )
    result = stage_gis(db, payload, manifest_sha="a2" * 32)

    assert result.staged_rows == len(ftp_headers)
    assert result.quarantined == {"key_incomplete": 0, "duplicate_row": 0, "parse_error": 0}
    with db.cursor() as cursor:
        cursor.execute("select count(*) from staging.nm_ocd_wells_gis")
        assert cursor.fetchone()[0] == len(ftp_headers)


def test_the_staged_points_are_transformed_into_storage_srid(db, ftp_headers, tmp_path):
    payload = gis_payload(tmp_path / "wells.geojsonl", ftp_headers)
    stage_gis(db, payload, manifest_sha="a3" * 32)

    with db.cursor() as cursor:
        cursor.execute("select distinct st_srid(geom) from staging.nm_ocd_wells_gis")
        assert cursor.fetchall() == [(4326,)]


def test_the_stage_derivation_cites_the_parity_rule_it_is_evidence_for(db, ftp_headers, tmp_path):
    payload = gis_payload(tmp_path / "wells.geojsonl", ftp_headers)
    result = stage_gis(db, payload, manifest_sha="a4" * 32)

    with db.cursor() as cursor:
        cursor.execute(
            "select rule_id from lineage.derivation_rules where derivation_id = %s",
            (result.parse_derivation_id,),
        )
        cited = {rule for (rule,) in cursor.fetchall()}

    assert {
        "cr_nm_wells_gis_api10_1",
        "cr_nm_wells_gis_datum_1",
        "cr_nm_wells_gis_walk_order_1",
        "cr_nm_wells_gis_parity_1",
    } <= cited


def test_nothing_canonical_is_written_by_this_source(db, ftp_headers, tmp_path):
    """Staging is the terminus: the parity measurement decides how it promotes, so promoting
    first would make the parity rule a rationalisation of a choice already made."""
    payload = gis_payload(tmp_path / "wells.geojsonl", ftp_headers)
    stage_gis(db, payload, manifest_sha="a5" * 32)

    with db.cursor() as cursor:
        cursor.execute("select count(*) from canonical.wells")
        assert cursor.fetchone()[0] == 0
        cursor.execute("select count(*) from canonical.well_spatial")
        assert cursor.fetchone()[0] == 0


def test_the_header_archive_still_names_itself_sole_authority(db, seeded) -> None:
    """Until the distance distribution is measured, no per-field preference is decided."""
    with db.cursor() as cursor:
        cursor.execute(
            "select spec from lineage.conformance_rules where rule_id = %s",
            ("cr_nm_wellhistory_header_precedence_1",),
        )
        spec = cursor.fetchone()[0]
        cursor.execute(
            "select spec from lineage.conformance_rules where rule_id = %s",
            ("cr_nm_wellhistory_header_precedence_2",),
        )
        corrected = cursor.fetchone()[0]

    assert set(spec["authority"].values()) == {"nm_ocd_wellhistory"}
    assert spec["second_source"] is None
    # A corrected successor exists and decides nothing: it names the promoter its ancestor
    # named wrongly, and carries the same authority and the same condition for the supersession
    # this measurement is actually for.
    assert set(corrected["authority"].values()) == {"nm_ocd_wellhistory"}
    assert corrected["second_source"] is None
    assert corrected["superseded_when"] == spec["superseded_when"]
