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
)

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
            "select count(*) from lineage.conformance_rules where rule_id like 'cr_blm\\_%'"
        )
        return int(cursor.fetchone()[0])
