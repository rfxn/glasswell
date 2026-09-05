"""Which basin a well is in, as a row per jurisdiction (R8).

`canonical.wells.basin` is a scope label from the ingest, not a geological finding: every
Texas well in the 55-county slice reads `permian` whether or not it is in the Permian, and the
label exists because `lineage.crs_registry` needs a basin to pick a compute CRS. 182,626 wells
carry no label at all. A well's basin is a cross-source mapping decision, and it existed only
in code.

These five rules decide a **different column** from the four `basin_scope` rules already
registered, and do not supersede them. `cr_mt_basin_scope_1` says Montana promotes no ingest
label and gives the measurement behind that -- Bakken is 4.6 percent of Montana -- and it is
still true. These say which published polygon the well's answering geometry falls in, which is
a question that column never answered. Both are served, side by side, with an agreement mark.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

BASIN_CONTEXT = "basin_context"

BASIN_CONTEXT_FROM = date(2026, 9, 3)

MART = "marts.well_basin_context"
REFRESHER = "glasswell.marts.well_basin_context:refresh_well_basin_context"

# v0.80 asks the surface point in every jurisdiction and registers that choice, so a later
# change to the lateral midpoint or the bottom hole is a supersession rather than a silent
# shift in what the same field means.
GEOMETRY_BASIS = "surface"

OUTSIDE = "outside_published_boundaries"

BOUNDARY_SET = {
    "publisher": "EIA",
    "rows": 48,
    "basins": 32,
    "plays": 16,
    "extent": "national",
    "membership_rule": "cr_eia_well_membership_1",
    "overlap_rule": "cr_eia_boundary_overlap_1",
    "taxonomy_rule": "cr_eia_boundary_taxonomy_1",
}

MEASURED_ON = "2026-09-03"

# Measured on the deployed spine, driven off canonical.wells_latest exactly as the mart is,
# with a lateral join to one containing basin polygon:
#   select left(l.api10,2), count(*), count(*) filter (where s.api10 is null),
#          count(*) filter (where s.api10 is not null and b.name is null),
#          count(*) filter (where b.name is not null)
#     from canonical.wells_latest l
#     left join canonical.well_spatial s on s.api10 = l.api10 and s.geom_type = 'surface'
#     left join lateral (...) b on true group by 1
# Re-measured at P4's build and unchanged from the 2026-09-02 reading it was written from.
COVERAGE: dict[str, dict[str, int]] = {
    "ND": {"wells": 43817, "inside": 43424, "outside": 393, "no_geometry": 0},
    "TX": {"wells": 359421, "inside": 344611, "outside": 10852, "no_geometry": 3958},
    "NM": {"wells": 142000, "inside": 137505, "outside": 4273, "no_geometry": 222},
    "MT": {"wells": 40626, "inside": 13062, "outside": 27564, "no_geometry": 0},
    "CO": {"wells": 0, "inside": 0, "outside": 0, "no_geometry": 0},
}

# The same question asked of the geometry table rather than of the well list, which is the basis
# the spec's four published shares are quoted on. Kept beside COVERAGE rather than instead of
# it because the two answers differ, and only for Montana: the difference is exactly the 1,400
# surface api10s with no well behind them (N-3), 561 of which fall in a published basin. A
# reader who checks the spec's numbers against the mart's has to be able to see why they differ
# without re-running either query.
GEOMETRY_DRIVEN: dict[str, dict[str, int]] = {
    "ND": {"surface_api10s": 43817, "inside": 43424},
    "TX": {"surface_api10s": 355463, "inside": 344611},
    "NM": {"surface_api10s": 141778, "inside": 137505},
    "MT": {"surface_api10s": 42026, "inside": 13623},
}

# The four shares as the spec publishes them, to the one decimal place it publishes them at.
PUBLISHED_SHARES = {"ND": 99.1, "TX": 96.9, "NM": 97.0, "MT": 32.4}

# Montana's whole difference between the two bases: api10s carrying a surface point and no row
# in wells_latest, and how many of them a published basin contains.
GEOMETRY_ONLY_MT = {"surface_api10s": 1400, "inside": 561}

# The Texas disagreement, measured the same way: of the 344,611 Texas wells whose surface point
# falls in a published basin, 10,896 fall in a basin that is not the `permian` the ingest
# labelled them, 10,030 of them in Fort Worth.
TEXAS_DISAGREEMENT = {
    "comparable": 344611,
    "disagreeing": 10896,
    "share": "0.0316",
    "by_polygon": {"FORT WORTH": 10030, "PALO DURO": 456, "MARFA": 410},
}

_LABEL_KEPT = (
    "the ingest scope label is kept on the row beside the polygon answer and marked as what it"
    " is, never overwritten: a disagreement with a handle is worth more than a silent"
    " correction, and a reader who has been reading the label for a year needs to see it move"
)


def _rule(
    code: str,
    rule_id: str,
    source_id: str,
    *,
    rule: str,
    rationale: str,
    evidence_url: str,
) -> dict[str, object]:
    coverage = COVERAGE[code]
    return {
        "rule_id": rule_id,
        "source_id": source_id,
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["basin"],
        "spec": {
            "decision": BASIN_CONTEXT,
            "module_function": REFRESHER,
            "version": "1",
            "contract_note": (
                "answers the basin from the published boundary set by point-in-polygon on the"
                " geometry named in geometry_basis, keeps the ingest scope label beside it and"
                " marks their agreement; it writes marts.well_basin_context and decides nothing"
                " about canonical.wells.basin"
            ),
            "mart": MART,
            "driven_off": "canonical.wells_latest",
            "geometry_basis": GEOMETRY_BASIS,
            "absent_class": OUTSIDE,
            "boundary_set": BOUNDARY_SET,
            "label_kept": _LABEL_KEPT,
            "measured_on": MEASURED_ON,
            "coverage": coverage,
            "does_not_supersede": (
                "the jurisdiction's basin_scope rule, which decides whether the ingest writes"
                " canonical.wells.basin at all. Two columns, two decisions, both served"
            ),
        },
        "code_ref": REFRESHER,
        "rule": rule,
        "rationale": rationale,
        "evidence_url": evidence_url,
        "effective_from": BASIN_CONTEXT_FROM,
    }


EIA_URL = "https://www.eia.gov/maps/map_data/SedimentaryBasins_US_EIA.zip"

# All five carry the boundary publisher's source rather than each jurisdiction's own well
# extract, because that is the file the decision rests on: the answer is a point-in-polygon
# against the EIA set, and the well extract only supplies the point. It also keeps every
# per-jurisdiction seeder's registry total where it was -- those counts are taken over a source
# prefix, and a rule of ours landing under one would move the number between two runs of an
# idempotent seed.
BOUNDARY_SOURCE = "eia_shale_plays"

BASIN_CONTEXT_RULES: tuple[dict[str, object], ...] = (
    _rule(
        "ND",
        "cr_nd_basin_context_1",
        BOUNDARY_SOURCE,
        rule=(
            "A North Dakota well's basin is the published boundary its surface point falls in."
            " The filed `williston` label is an ingest scope label and is kept beside it."
        ),
        rationale=(
            "Measured on the deployed spine 2026-09-03: 43,424 of 43,817 North Dakota wells"
            " have a surface point inside a published basin polygon (99.1 percent) and 393 fall"
            " outside every one of them. The filed label reads `williston` on all 43,817 rows,"
            " which is the ingest's slice rather than a finding, so the two agree almost"
            " everywhere and the 393 are the wells where the honest answer is that they are"
            f" outside every basin the publisher draws. Because they agree, {_LABEL_KEPT}."
        ),
        evidence_url=EIA_URL,
    ),
    _rule(
        "TX",
        "cr_tx_basin_context_1",
        BOUNDARY_SOURCE,
        rule=(
            "A Texas well's basin is the published boundary its surface point falls in. The"
            " filed `permian` label is an ingest scope label, is kept beside it, and disagrees"
            " with the polygon for part of the slice."
        ),
        rationale=(
            "This is the rule that matters, because Texas is where the scope label and the map"
            " part company. `canonical.wells.basin` reads `permian` on all 359,421 Texas rows"
            " because the ingest took a 55-county slice and lineage.crs_registry needs a basin"
            " to pick a compute CRS, not because a geologist put those wells in the Permian."
            " Measured on the deployed spine 2026-09-03: 344,611 Texas wells have a surface"
            " point inside a published basin, and 10,896 of them (3.16 percent) fall in a basin"
            " that is not the Permian -- 10,030 in Fort Worth, 456 in Palo Duro, 410 in Marfa."
            " 10,852 fall outside every published boundary and 3,958 have no surface point at"
            f" all. The disagreement is served rather than hidden: {_LABEL_KEPT}."
        ),
        evidence_url=EIA_URL,
    ),
    _rule(
        "MT",
        "cr_mt_basin_context_1",
        BOUNDARY_SOURCE,
        rule=(
            "A Montana well's basin is the published boundary its surface point falls in, and"
            " for two thirds of the state that is outside every boundary the publisher draws."
            " Montana files no ingest label, so there is nothing to compare."
        ),
        rationale=(
            "Montana carries no ingest scope label, by cr_mt_basin_scope_1, which measured that"
            " Bakken is the fifth formation in the state by row count at 4.6 percent and"
            " declined to extend the Williston across the state line. That rule stands and this"
            " one does not supersede it: it decides a different column. What this adds is the"
            " polygon answer, and the answer is smaller than it looks. Measured on the deployed"
            " spine 2026-09-03, 13,062 of 40,626 Montana wells have a surface point inside a"
            " published basin and 27,564 (67.8 percent of the wells) fall outside every one;"
            " asked of the geometry table instead, which counts the 1,400 surface points"
            " with no well behind them, it is 13,623 of 42,026 inside and 67.6 percent"
            " outside. So the Montana win is `outside_published_boundaries`, with the"
            " boundary set and its vintage named"
            " -- a finding about what the publisher draws, not a failure of the well -- and for"
            " the 13,062 it is a basin nobody had before."
        ),
        evidence_url=EIA_URL,
    ),
    _rule(
        "NM",
        "cr_nm_basin_context_1",
        BOUNDARY_SOURCE,
        rule=(
            "A New Mexico well's basin is the published boundary its surface point falls in."
            " New Mexico files no ingest label, so there is nothing to compare."
        ),
        rationale=(
            "New Mexico is where this migration earns its keep. cr_nm_wellhistory_basin_scope_1"
            " leaves every one of the 142,000 wells untagged, on purpose, and that rule stands:"
            " it decides whether the ingest writes a label, and this decides what the published"
            " boundaries say. Measured on the deployed spine 2026-09-03: 137,505 of 142,000"
            " New Mexico wells have a surface point inside a published basin (97.0 percent),"
            " 4,273 fall outside every one and 222 have no surface point. Those 137,505 wells"
            " go from no basin at all to a basin with a boundary set, a vintage and a handle."
        ),
        evidence_url=EIA_URL,
    ),
    _rule(
        "CO",
        "cr_co_basin_context_1",
        BOUNDARY_SOURCE,
        rule=(
            "A Colorado well's basin is the published boundary its surface point falls in."
            " Colorado files no ingest label, so there is nothing to compare."
        ),
        rationale=(
            "Registered on the same terms as its neighbours and measured at zero, because the"
            " Colorado registration is in the registry and its wells are not yet in the spine"
            " the measurement above was taken on. Recorded as zero rather than omitted: a"
            " jurisdiction with no rule serves no basin context at all, and that would read as"
            " a decision nobody made rather than as a population nobody has loaded. The mart"
            " answers for Colorado the day its wells land, with no code change."
        ),
        evidence_url=EIA_URL,
    ),
)

_INSERT = """
insert into lineage.conformance_rules
    (rule_id, rule_family, supersedes_rule_id, source_id, stage, applies_to_fields, rule_kind,
     spec, rule, rationale, evidence_url, code_ref, effective_from)
values (%(rule_id)s, %(rule_family)s, %(supersedes_rule_id)s, %(source_id)s, %(stage)s,
        %(applies_to_fields)s, %(rule_kind)s, %(spec)s, %(rule)s, %(rationale)s,
        %(evidence_url)s, %(code_ref)s, %(effective_from)s)
on conflict do nothing
"""


def _row(rule: dict[str, object]) -> dict[str, object]:
    rule_id = str(rule["rule_id"])
    return {
        **rule,
        "rule_family": rule_id.rsplit("_", 1)[0],
        "spec": Jsonb(rule["spec"]),
        "code_ref": rule.get("code_ref"),
        "supersedes_rule_id": rule.get("supersedes_rule_id"),
        "effective_from": rule.get("effective_from", BASIN_CONTEXT_FROM),
    }


def seed_conformance_basin_context(connection: psycopg.Connection) -> int:
    """The five rules. Their registration is declared in seed.jurisdictions and written by
    seed_jurisdictions, which is the one writer test_jurisdiction_parity reads. Counted over
    its own ids, so no sibling seeder's registry total moves when this grows."""
    # Registers the boundary publisher's source itself, so this seeder can run ahead of every
    # per-prefix count without waiting for the registry that usually declares it. Imported
    # here rather than at module scope: seed.jurisdictions reads this module's decision name,
    # and conformance_basins reads seed.jurisdictions.
    from glasswell.seed.conformance_basins import seed_sources_basins

    seed_sources_basins(connection)
    rule_ids = [str(rule["rule_id"]) for rule in BASIN_CONTEXT_RULES]
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT, [_row(rule) for rule in BASIN_CONTEXT_RULES])
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_id = any(%s)",
            (rule_ids,),
        )
        return int(cursor.fetchone()[0])
