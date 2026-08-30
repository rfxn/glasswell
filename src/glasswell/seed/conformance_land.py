"""Land-grid conformance rules and the BLM sources they attach to (R8, M1-4).

Dual-homed with migration 034: an already-migrated database gets these rows there, a fresh
one gets them here, and the content is the same in both homes.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

EFFECTIVE_FROM = date(2026, 8, 22)

SERVICE_URL = (
    "https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI_NAD83/MapServer"
)

BLM_LICENSE_NOTE = (
    "US federal government work (17 U.S.C. §105); no licence or terms-of-use string is"
    " published on the service and no redistribution clause was found. Accuracy disclaimer"
    " only. Reachability verified by anonymous query 2026-08-22."
)

LAND_SOURCES: tuple[dict[str, object], ...] = (
    {
        "source_id": "blm_plss_townships",
        "name": "BLM national CadNSDI PLSS townships (NAD83 service, layer 1)",
        "jurisdiction": "ND",
        "license_note": BLM_LICENSE_NOTE,
        "redistributable": False,
    },
    {
        "source_id": "blm_plss_sections",
        "name": "BLM national CadNSDI PLSS sections / first division (NAD83 service, layer 2)",
        "jurisdiction": "ND",
        "license_note": BLM_LICENSE_NOTE,
        "redistributable": False,
    },
)

LAND_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "cr_blm_plss_publisher_1",
        "source_id": "blm_plss_sections",
        "stage": "conform",
        "rule_kind": "code_ref",
        "applies_to_fields": ["geom", "plssid", "frstdivid"],
        "spec": {
            "module_function": "glasswell.ingest.blm_plss:LAYERS",
            "version": "1",
            "publisher": "BLM_Natl_PLSS_CadNSDI_NAD83",
            "rejected_publishers": [
                "BLM_MT_ND_SD_CadNSDI (regional)",
                "NM OCD OCD_PLSS (mirror)",
            ],
            "divergence_measured": {
                "nd_townships": {"national": 2067, "regional": 2067},
                "nd_first_division": {"national": 71486, "regional": 71486},
                "nd_second_division": {"national": 1131664, "regional": 1131639},
                "nm_townships": {"national": 3299, "mirror": 3283},
                "nm_first_division": {"national": 110237, "mirror": 109995},
            },
            "contract_note": "canonical.land_units and both land tile layers carry this"
            " publisher's own unit ids verbatim (plssid, frstdivid); the ingest module is the"
            " executor, and a different publisher is a superseding row, not a code change",
        },
        "rule": "Serve the PLSS grid from the BLM national CadNSDI NAD83 service; the regional"
        " and mirror publishers of the nominally identical grid are cross-checks, not sources.",
        "rationale": (
            "Three publishers of the same BLM CadNSDI grid disagree, measured 2026-08-21"
            " (data-sources-land.md §2): ND second division differs by 25 features between the"
            " national and regional services, and NM diverges by 16 townships and 242"
            " first-division features against the OCD mirror. ND townships and first division"
            " agree to the feature, so the grain this repository ingests is publisher-stable"
            " today — but which service is authoritative is still a choice three regulators"
            " would answer differently, so it is this row. The NAD83 sibling is taken over the"
            " web-mercator default because storage takes a datum, not a projection."
        ),
        "evidence_url": SERVICE_URL,
        "code_ref": "src/glasswell/ingest/blm_plss.py",
    },
    {
        "rule_id": "cr_blm_plss_datum_1",
        "source_id": "blm_plss_sections",
        "stage": "conform",
        "rule_kind": "datum_transform",
        "applies_to_fields": ["geom"],
        "spec": {
            "source_epsg": 4269,
            "target_epsg": 4326,
            "detect": {"service_sr_wkid": 4269},
        },
        "rule": "Transform NAD83 land-grid polygons to EPSG:4326 before they reach storage.",
        "rationale": (
            "The service's own spatialReference is wkid 4269 (NAD83), read from the layer JSON"
            " on every fetch and recorded on the manifest. Storage is always 4326 and the"
            " transform is recorded as a derivation even though the shift is sub-metre: no"
            " coordinate reaches storage untransformed and unrecorded (same rule as"
            " cr_nd_datum_1)."
        ),
        "evidence_url": SERVICE_URL,
    },
    {
        "rule_id": "cr_blm_plss_scope_1",
        "source_id": "blm_plss_sections",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["plssid"],
        "spec": {
            "where": "PLSSID LIKE 'ND%'",
            "layers": ["townships", "sections"],
            "state": "ND",
        },
        "rule": "Harvest the national grid's North Dakota slice only: PLSSID LIKE 'ND%' on"
        " both the township and section layers.",
        "rationale": (
            "PLSSID is state-prefixed (sample ND051640N1030W0), verified by count queries that"
            " reconcile with the published ND totals (2,067 townships, 71,486 sections). The"
            " slice is a scope decision the fetch applies server-side, so it is a row rather"
            " than a where-clause only the code can see; widening to NM is a new rule, not an"
            " edit."
        ),
        "evidence_url": SERVICE_URL + "/2",
    },
    {
        "rule_id": "cr_land_agg_membership_1",
        "source_id": "blm_plss_sections",
        "stage": "join",
        "rule_kind": "code_ref",
        "applies_to_fields": ["geom", "land_unit_id", "api10"],
        "spec": {
            "module_function": "glasswell.marts.land_metrics:refresh_land_metrics",
            "version": "1",
            "assign_by": "lateral_midpoint_else_surface",
            "anchor": {
                "lateral": "the newest filed lateral row (created_at desc, ties broken by"
                " geom_key): 695 ND wells carry more than one filed lateral in a single"
                " promotion batch, 256 of them with midpoints in different sections, so the"
                " pick is stated rather than plan-dependent. Its midpoint is"
                " ST_LineInterpolatePoint(ST_LineMerge(lateral), 0.5) when the merge yields"
                " a single LineString; ST_ClosestPoint(lateral, ST_Centroid(lateral)) for"
                " the multi-part remainder (5 of 22,263 measured)",
                "no_lateral": "the surface hole point, which for a vertical well is the"
                " producing location itself",
                "midpoint_orphan": "a midpoint resolving no section falls back to the"
                " surface hole: 163 ND wells measured (state-line and grid-edge laterals)"
                " carrying 2,071,625 bbl of observed liquid that would otherwise appear in"
                " no cell",
            },
            "tie_break": "min(land_unit_id) when the anchor intersects more than one section"
            " (0 measured today; the dedupe is structural, not observed)",
            "township_membership": "the parent township of the assigned section via the"
            " plssid join, never an independent point test — a well is in the township of"
            " its section",
            "unassigned": "a well whose midpoint and surface hole both resolve no land"
            " unit is excluded from every cell; the refresh derivation params count the"
            " exclusions twice over — in total (Texas is expected to be wholly unassigned"
            " until a TX land grid exists) and for the grid's own states, where any nonzero"
            " count is an anomaly (0 ND wells measured today under the surface fallback)",
            "observed_only": "whole-well observed sums: each well lands in exactly one"
            " section, no length-weighted apportionment, no interpolation, no estimate."
            " Fractional allocation is a superseding rule with Protocol 4D obligations,"
            " not an edit",
            "contract_note": "marts.land_metrics_tile and both metric tile layers carry"
            " whole-well sums under this membership; the mart module is the executor, and a"
            " different membership (apportionment, bottomhole) is a superseding row, not a"
            " code change",
            "evidence_measured": {
                "measured_on": "2026-08-22, VM 111 canonical (73,512 land units, 398,403"
                " production rows)",
                "nd_wells": 43817,
                "with_surface_point": 43817,
                "with_lateral": 22263,
                "with_bottomhole": 0,
                "laterals_crossing_2plus_sections": {
                    "count": 18903, "of": 22261, "share": "84.9%"},
                "midpoint_section_differs_from_surface": {
                    "count": 10464, "of": 22100, "share": "47.3%"},
                "liquid_volume_on_differing_wells_bbl": {
                    "bbl": 107776020, "of_bbl": 187984167, "share": "57.33%",
                    "population": "well-entity production rows only, under the"
                    " deterministic lateral pick"},
                "township_grain_differs": {"count": 1798, "of": 22100, "share": "8.1%"},
                "multi_lateral_wells": {"count": 695, "with_differing_midpoints": 256},
                "midpoint_orphans": {
                    "count": 163, "liquid_bbl": 2071625,
                    "disposition": "fallback to surface hole"},
            },
        },
        "rule": "A well belongs to the section holding its lateral midpoint when it has a"
        " filed lateral, and the section holding its surface hole otherwise; townships"
        " inherit through the section's parent. Sums are whole-well and observed-only.",
        "rationale": (
            "Three candidate memberships were measured before choosing (M2-3). Bottomhole"
            " is unavailable for the grid's wells: canonical.well_spatial holds zero ND"
            " bottomhole geometries (the 360,434 on file are all Texas)."
            " Surface-point membership is complete (43,817/43,817) but misplaces the"
            " producing footprint: 84.9% of ND laterals cross two or more sections, the"
            " lateral midpoint sits in a different section than the surface hole for 47.3%"
            " of laterals — and volume-weighted that is 57.33% of every observed ND liquid"
            " barrel (107.78M of 187.98M, well-entity rows only), because pads cluster"
            " surface holes in one"
            " section while the rock that produced sits under the next. At section grain a"
            " surface-point choropleth is a pad map wearing a production map's title. The"
            " lateral midpoint is the arc-length centre of the filed bore — a"
            " producing-interval proxy that keeps each well whole in one cell,"
            " observed-only, with the surface hole as the exact answer for verticals."
            " Length-weighted apportionment across crossed sections was rejected for v1: it"
            " manufactures fractional well-months nothing observed, which is allocation"
            " modelling and takes a superseding rule carrying its spacing assumption per"
            " Protocol 4D. At township grain the same choice moves only 8.1% of laterals,"
            " so the township surface is robust to it either way."
        ),
        "evidence_url": "https://gis.dmr.nd.gov/downloads/oilgas/shapefile/"
        "OGD_Horizontals_Line.zip",
        "code_ref": "src/glasswell/marts/land_metrics.py",
    },
)

_MEMBERSHIP_1 = next(
    rule for rule in LAND_RULES if rule["rule_id"] == "cr_land_agg_membership_1"
)

# The membership itself is unchanged, which is exactly why this is a superseding row and not a
# code change: _1's own contract_note says a different membership is a superseding row, and no
# different membership is being proposed. What changes is that the scope the grid covers is now
# stated beside the figure rather than left to be inferred from a total.
MEMBERSHIP_2: dict[str, object] = {
    **_MEMBERSHIP_1,
    "rule_id": "cr_land_agg_membership_2",
    "supersedes_rule_id": "cr_land_agg_membership_1",
    "effective_from": date(2026, 8, 30),
    "spec": {
        **dict(_MEMBERSHIP_1["spec"]),  # type: ignore[arg-type]
        "version": "2",
        "grid_scope_api_prefixes": ["33"],
        "unassigned": "a well whose midpoint and surface hole both resolve no land unit is"
        " excluded from every cell; the refresh derivation params count the exclusions three"
        " ways — in total, for the grid's own states where any nonzero count is an anomaly,"
        " and for wells outside the states the PLSS grid covers at all, which is where every"
        " Texas and New Mexico well falls until a grid exists for them",
        "unassigned_populations_measured": {
            "measured_on": "2026-08-29, VM 111 canonical.well_spatial by state and geom_type",
            "nd_surface": 43817,
            "tx_surface": 355463,
            "nm_surface": 0,
            "nm_surface_after_the_header_promotion": 141778,
        },
    },
    "rule": "A well belongs to the section holding its lateral midpoint when it has a filed"
    " lateral, and the section holding its surface hole otherwise; townships inherit through"
    " the section's parent. Sums are whole-well and observed-only. The membership universe is"
    " every well with a surface point in any state, and the served unassigned count says which"
    " of those the grid does not cover.",
    "rationale": (
        "The membership is unchanged from cr_land_agg_membership_1 and this row supersedes it"
        " for one reason: the universe was never state-scoped, and 355,463 Texas surface points"
        " are already in it. Filtering the universe to the grid's states would have collapsed a"
        " served figure from about 355,463 to about zero while describing a scope that has not"
        " changed — the grid covers exactly the states it covered yesterday, and only our"
        " description of it is becoming explicit. A restatement should record a change in the"
        " world or in our reading of it, not a change in our vocabulary. So the scope is stated"
        " beside the existing figure as a third counter rather than applied to it as a filter,"
        " which is both cheaper and truer. New Mexico's 141,778 surface points join the"
        " out-of-scope population when the header promotion lands, and any figure whose inputs"
        " are state-truncated says so on the figure."
    ),
}

LAND_RULES = (*LAND_RULES, MEMBERSHIP_2)

_INSERT_SOURCE = """
insert into lineage.sources (source_id, name, jurisdiction, license_note, redistributable)
values (%(source_id)s, %(name)s, %(jurisdiction)s, %(license_note)s, %(redistributable)s)
on conflict do nothing
"""

_INSERT_RULE = """
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
        "evidence_url": rule.get("evidence_url"),
        "supersedes_rule_id": rule.get("supersedes_rule_id"),
        "effective_from": rule.get("effective_from", EFFECTIVE_FROM),
    }


def seed_sources_land(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_SOURCE, LAND_SOURCES)
    return len(LAND_SOURCES)


def seed_conformance_land(connection: psycopg.Connection) -> int:
    """Rule ids are immutable: a change is a new row with supersedes_rule_id (SB-07 §6.2)."""
    seed_sources_land(connection)
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_RULE, [_row(rule) for rule in LAND_RULES])
        cursor.execute(
            "select count(*) from lineage.conformance_rules"
            " where rule_id like 'cr_blm\\_%' or rule_id like 'cr_land\\_%'"
        )
        return int(cursor.fetchone()[0])
