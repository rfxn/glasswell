"""GW_SEED for the Colorado shots: enough of a real jurisdiction to photograph.

`connection` is bound by tests/support/serve_branch.py after the base seeds, which already
carry Colorado's registration, its rules and its codebook. What this adds is data: wells across
the statuses and location-qualifier classes a reader has to be able to tell apart, one well with
production under the dual write so its card renders both a chart and a cumulative frame, the
tile rows the map draws, and a measured well count so the subtitle and the legend census are
photographed with a number rather than with a pending mark.
"""
from datetime import date
from decimal import Decimal

from glasswell.seed.jurisdictions import CO_REGISTERED_ON
from tests.support.seed import (
    seed_derivation,
    seed_manifest,
    seed_production,
    seed_well,
    seed_well_spatial,
)

# Denver-Julesburg, so the wells land where a reader expects Colorado to be.
ORIGIN = (-104.72, 40.32)
PRODUCER = "0512324638"
SUSPENDED = "0512324700"

# One well per class a shot has to distinguish, with the filed code and the qualifier that
# makes the point's own quality readable.
WELLS = (
    (PRODUCER, "PR", "actual", "CROSSBOW 12-7HN", 2021),
    (SUSPENDED, "SO", "planned", "WATTENBERG STATE 3-14", 2019),
    ("0512324701", "PA", "actual", "PLATTE RIVER 1", 1984),
    ("0512324702", "AL", "planned", "NIOBRARA UNIT 22-3", None),
    ("0512324703", "SI", "actual", "GREELEY 8-11H", 2016),
    ("0512324704", "TA", "actual", "LARIMER 4-9", 2008),
    ("0512324705", "AP", "planned", "KERSEY 31-2HN", None),
    ("0512324706", "IJ", "actual", "DISPOSAL 1-32", 2011),
    ("0512324707", "EP", "planned", "EATON 7-19", None),
    ("0512324708", "WO", "planned", "SEVERANCE 5-8HN", 2026),
    ("0512324709", "AC", "actual", "STORAGE OBSERVATION 2", 1998),
    ("0512324710", "DG", "planned", "WINDSOR 14-21HN", 2026),
)

manifest = seed_manifest(
    connection, sha256="c0" * 32, source_id="co_ecmc_wells_shp"  # noqa: F821
)
derivation = seed_derivation(connection)  # noqa: F821

for index, (api10, status, qualifier, name, spud) in enumerate(WELLS):
    seed_well(
        connection,  # noqa: F821
        api10=api10,
        state_code="05",
        basin=None,
        county_code_at_permit="123",
        # Both are North Dakota's, and the fixture defaults to them. A Colorado well carries
        # neither: NDIC's file number is one regulator's own, and no PLSS grid is loaded for
        # this state, which is one of the three reasons its inventory is a registered refusal.
        ndic_file_no=None,
        land_unit_label=None,
        operator_name_reported="CROSSBOW ENERGY LLC",
        well_name=name,
        status_canonical=None,
        status_reported=status,
        well_type_reported="GW" if index % 2 else "OW",
        spud_date=date(spud, 6, 1) if spud else None,
        effective_from=CO_REGISTERED_ON,
        manifest_id=manifest,
        derivation_id=derivation,
    )
    seed_well_spatial(
        connection,  # noqa: F821
        api10=api10,
        geom_type="surface",
        wkt=f"POINT({ORIGIN[0] + index * 0.04:.4f} {ORIGIN[1] + (index % 4) * 0.03:.4f})",
        location_qualifier=qualifier,
        source_datum="NAD_1983_UTM_Zone_13N",
        transform_rule_id="cr_co_wells_datum_1",
        manifest_id=manifest,
        derivation_id=derivation,
    )

# The producing well, as the dual write lands it: two completions in one month and one in the
# next, plus the well row carrying their exact sum. Without that row the card's chart is empty.
production_manifest = seed_manifest(
    connection, sha256="c1" * 32, source_id="co_ecmc_monthly_prod"  # noqa: F821
)
MONTHS = (
    (date(2025, 12, 1), (Decimal("980"), Decimal("410"))),
    (date(2026, 1, 1), (Decimal("905"), Decimal("388"))),
    (date(2026, 2, 1), (Decimal("861"), Decimal("352"))),
    (date(2026, 3, 1), (Decimal("822"),)),
    (date(2026, 4, 1), (Decimal("790"),)),
)
for month, completions in MONTHS:
    for pool, volume in enumerate(completions):
        if len(completions) == 1:
            continue
        for stream, factor in (("oil", 1), ("gas", 3), ("water", 2)):
            seed_production(
                connection,  # noqa: F821
                api10=PRODUCER,
                production_month=month,
                report_vintage=date(2026, 8, 14),
                volume=volume * factor,
                stream=stream,
                source_id="co_ecmc_monthly_prod",
                entity_type="well_completion_pool",
                entity_key=f"{PRODUCER}:00:CDMV{pool}:200221",
                reporting_level="well_completion_pool",
                well_completion_pool=f"00:CDMV{pool}:200221",
                manifest_id=production_manifest,
                derivation_id=derivation,
            )
    aggregated = len(completions) > 1
    for stream, factor in (("oil", 1), ("gas", 3), ("water", 2)):
        seed_production(
            connection,  # noqa: F821
            api10=PRODUCER,
            production_month=month,
            report_vintage=date(2026, 8, 14),
            volume=sum(completions, Decimal(0)) * factor,
            stream=stream,
            source_id="co_ecmc_monthly_prod",
            entity_type="well",
            entity_key=PRODUCER,
            reporting_level="well_completion_pool" if aggregated else "well",
            well_completion_pool=None if aggregated else "00:CDMV0:200221",
            aggregation="sum_over_pools" if aggregated else None,
            manifest_id=production_manifest,
            derivation_id=derivation,
        )

with connection.cursor() as cursor:  # noqa: F821
    cursor.executemany(
        "insert into marts.co_wells_tile (api10, operator_name, status_canonical,"
        " status_reported, well_type_reported, county_code, spud_year, loc_qual_class,"
        " geometry_provenance, geom, derivation_id)"
        " select w.api10, w.operator_name_reported, r.resolved_status, w.status_reported,"
        "        w.well_type_reported, w.county_code_at_permit,"
        "        extract(year from w.spud_date)::int, s.location_qualifier, s.geom_type,"
        "        s.geom, %s"
        "   from canonical.wells w"
        "   join canonical.well_spatial s on s.api10 = w.api10 and s.geom_type = 'surface'"
        "   left join canonical.status_resolution r"
        "     on r.for_state_code = w.state_code and r.for_status_reported = w.status_reported"
        "  where w.api10 = %s"
        " on conflict (api10) do nothing",
        [(derivation, api10) for api10, *_rest in WELLS],
    )
    # A measured count with the date beside it, so the subtitle and the legend census are
    # photographed serving a number rather than a pending mark.
    cursor.execute(
        "insert into lineage.jurisdiction_well_counts (jurisdiction_code, measured_on,"
        " well_count, derivation_id) values ('CO', %s, %s, %s) on conflict do nothing",
        (date(2026, 9, 2), len(WELLS), derivation),
    )
connection.commit()  # noqa: F821
print(f"planted {len(WELLS)} Colorado wells, {PRODUCER} producing under the dual write")

# The cumulative mart, refreshed so the card's frame carries real totals and the span sentence
# beside them rather than "not in the snapshot". Colorado is in the mart's population by
# registration -- its `cumulatives_scope` row -- and the well row the dual write laid down is
# what the mart reads.
from glasswell.lineage.capture import lineage_session  # noqa: E402
from glasswell.lineage.models import DeriveEnvironment  # noqa: E402
from glasswell.lineage.store import PostgresRecorder  # noqa: E402
from glasswell.marts.cumulatives import refresh_well_cumulatives  # noqa: E402

with lineage_session(
    recorder=PostgresRecorder(connection),  # noqa: F821
    environment=DeriveEnvironment(env_id="env_test", code_version="shots", code_dirty=False),
):
    refreshed = refresh_well_cumulatives(connection)  # noqa: F821
connection.commit()  # noqa: F821
print(f"refreshed the cumulative mart: {refreshed.row_counts}")
