"""GW_SEED for the v0.81 status-truth shots: five jurisdictions, and the absence class in two.

`connection` is bound by tests/support/serve_branch.py after the base seeds, which already
carry every registration, its rules and its codebook. What this adds is data the shots need:
wells in all five jurisdictions so the legend's rows, the layer panel and the hover card are
photographed against a real canvas, and Texas twice over -- one well whose source filed a code
and one whose source filed none -- because the whole track is about telling those two apart.

The marts are refreshed through the shipped engine rather than hand-inserted, so what a shot
photographs is what a deploy would draw.
"""
from datetime import date

from glasswell.lineage.capture import lineage_session
from glasswell.lineage.models import DeriveEnvironment
from glasswell.lineage.store import PostgresRecorder
from glasswell.marts.counts import refresh_jurisdiction_counts
from glasswell.marts.wells import refresh_for
from glasswell.seed.jurisdictions import CO_REGISTERED_ON
from tests.support.seed import seed_derivation, seed_manifest, seed_well, seed_well_spatial

# api10, filed code, promoted class, well type, name, longitude, latitude. A filed code with no
# promoted class is a read-time jurisdiction; a filed code with one is a promotion; and a well
# with neither is the absence class on its plainest reading, which is what all 68,186 Texas
# wells with no class are on the deployed spine.
WELLS = (
    ("3305399801", "A", "active", "OG", "BILL 14-23 1H", -103.62, 47.81, "nd_gis_wells"),
    ("3305399802", "PA", "plugged", "OG", "TIOGA 2-11", -103.55, 47.86, "nd_gis_wells"),
    ("3305399803", "CONF", "confidential", "OG", "SANISH 9-4H", -102.98, 47.92, "nd_gis_wells"),
    ("3305399804", "SWD", "active", "SWD", "STATE DISPOSAL 1", -103.40, 47.74, "nd_gis_wells"),
    ("4238399801", "PRODUCING", "active", "OG", "MIDLAND 12-3H", -102.31, 31.92,
     "tx_gis_wells_county"),
    ("4238399802", "INJECTION", "service", "WI", "PERMIAN INJECTOR 4", -102.24, 31.86,
     "tx_gis_wells_county"),
    # The one the track exists for: the RRC filed no status at all, so no promotion wrote a
    # class and no map can resolve one. It is the absence class, and the card says which case.
    ("4238399803", None, None, "OG", "GLASSCOCK 7-19", -102.18, 31.98, "tx_gis_wells_county"),
    ("3001599801", "A", None, "OG", "EDDY 21-8H", -104.02, 32.42, "nm_ocd_wellhistory"),
    ("3001599802", "P", None, "OG", "LEA 3-14", -103.72, 32.36, "nm_ocd_wellhistory"),
    ("3001599803", "Q", None, "WI", "CARLSBAD DISPOSAL 2", -104.18, 32.28, "nm_ocd_wellhistory"),
    ("2508399801", "Producing", "active", "OG", "ELM COULEE 4-2H", -104.86, 47.62,
     "mt_gis_wells"),
    ("2508399802", "Shut In", "inactive", "OG", "RICHLAND 9-11", -104.62, 47.55, "mt_gis_wells"),
    ("2508399803", "P&A - Approved", "plugged", "OG", "CEDAR CREEK 1", -104.40, 46.95,
     "mt_gis_wells"),
    # The fourth disposal well. §11 exit 11 names MT, TX and NM, and the hover has to be
    # photographed on each: an injection code filed by a regulator that publishes no codebook
    # for it is the case the line's second sentence exists for.
    ("2508399804", "Active Injection", "active", "WI", "MBOGC DISPOSAL 3", -104.70, 47.58,
     "mt_gis_wells"),
    ("0512399801", "PR", None, "OW", "CROSSBOW 12-7HN", -104.72, 40.32, "co_ecmc_wells_shp"),
    ("0512399802", "AL", None, "OW", "NIOBRARA UNIT 22-3", -104.60, 40.38, "co_ecmc_wells_shp"),
    ("0512399803", "SO", None, "GW", "WATTENBERG STATE 3-14", -104.50, 40.26,
     "co_ecmc_wells_shp"),
)

manifests: dict[str, str] = {}
derivation = seed_derivation(connection)  # noqa: F821
for index, source in enumerate(sorted({row[7] for row in WELLS})):
    manifests[source] = seed_manifest(
        connection,  # noqa: F821
        sha256=f"{index + 1:02d}" * 32,
        source_id=source,
    )

for api10, filed, promoted, well_type, name, lon, lat, source in WELLS:
    seed_well(
        connection,  # noqa: F821
        api10=api10,
        state_code=api10[:2],
        basin="williston" if api10[:2] in ("33", "25") else None,
        county_code_at_permit="053",
        ndic_file_no="22023" if api10.startswith("33") else None,
        land_unit_label="151N-101W-11" if api10.startswith("33") else None,
        operator_name_reported="CROSSBOW ENERGY LLC",
        well_name=name,
        status_canonical=promoted,
        status_reported=filed,
        well_type_reported=well_type,
        spud_date=date(2019, 5, 27),
        effective_from=CO_REGISTERED_ON,
        manifest_id=manifests[source],
        derivation_id=derivation,
    )
    seed_well_spatial(
        connection,  # noqa: F821
        api10=api10,
        geom_type="surface",
        wkt=f"POINT({lon:.4f} {lat:.4f})",
        manifest_id=manifests[source],
        derivation_id=derivation,
    )
connection.commit()  # noqa: F821

with lineage_session(
    recorder=PostgresRecorder(connection),  # noqa: F821
    environment=DeriveEnvironment(env_id="env_test", code_version="shots", code_dirty=False),
):
    for code in ("ND", "TX", "NM", "MT", "CO"):
        refresh_for(connection, code)  # noqa: F821
    # Every registered class measured, zeros included and the absence class among them, so the
    # legend's rows are photographed with numbers rather than with a pending mark.
    counts = refresh_jurisdiction_counts(connection, measured_on=date(2026, 9, 3))  # noqa: F821
connection.commit()  # noqa: F821
print(f"planted {len(WELLS)} wells over five jurisdictions; counts {counts.rows} rows")
