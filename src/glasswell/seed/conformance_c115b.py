"""C-115B conformance rules, the waste vocabulary, and the source they attach to (R8, M1-9).

Dual-homed with migration 036: an already-migrated database gets these rows there, a fresh one
gets them here, and the content is the same in both homes.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

EFFECTIVE_FROM = date(2026, 8, 22)

SERVICE_URL = (
    "https://gis.emnrd.nm.gov/arcgis/rest/services/OCDPUB/C115B_NaturalGasWaste/FeatureServer"
)
LAYER_URL = f"{SERVICE_URL}/0"

C115B_LICENSE_NOTE = (
    "New Mexico public record served from an explicitly public ArcGIS endpoint with Extract"
    " enabled. copyrightText is empty and the service publishes no terms-of-use string; no"
    " redistribution clause was found. Reachability and the empty copyright verified by"
    " anonymous query 2026-08-22. EMNRD/OCD attributed as a courtesy."
)

C115B_SOURCES: tuple[dict[str, object], ...] = (
    {
        "source_id": "nm_c115b_upstream",
        "name": "NM OCD C-115B natural gas waste, upstream by well API (FeatureServer layer 0)",
        "jurisdiction": "NM",
        "license_note": C115B_LICENSE_NOTE,
        "redistributable": True,
    },
)

WASTE_TYPE_ROWS: tuple[dict[str, object], ...] = (
    {"waste_type_raw": "F", "waste_type_canonical": "flared"},
    {"waste_type_raw": "V", "waste_type_canonical": "vented"},
)

C115B_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "cr_nm_c115b_source_1",
        "source_id": "nm_c115b_upstream",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["id", "reporting_period", "waste_type", "volume"],
        "spec": {
            "service_url": SERVICE_URL,
            "layer_id": 0,
            "layer_name": "C-115B Upstream by Well API",
            "where": "1=1",
            "grain": "well API x reporting_period x waste_type",
            "rejected_sources": [
                "OCDPUB/C115B_NaturalGasWaste/MapServer/0 (same rows; declares no objectIdField"
                " and capabilities Query,Map,Data rather than Query,Extract)",
                "OCDView/Venting_Flaring (stale at C115Period 202207, property grain, and"
                " self-described as for demo purposes only)",
            ],
            "window": {
                "kind": "rolling",
                "months": 13,
                "measured_on": "2026-08-22",
                "min": 202507,
                "max": 202607,
            },
        },
        "rule": "Capture well-level flaring and venting from OCDPUB/C115B_NaturalGasWaste layer"
        " 0 on the FeatureServer, whole layer, every month.",
        "rationale": (
            "Three NM services publish something called venting and flaring and only one of"
            " them is this. OCDView/Venting_Flaring is the layer the obvious search finds: it"
            " stopped updating at C115Period 202207, reports at property grain rather than"
            " well, joins no identity spine, and its own description says it is for demo"
            " purposes only. The MapServer sibling of the chosen service carries the same"
            " 71,447 rows but declares no objectIdField and advertises Query,Map,Data where the"
            " FeatureServer advertises Query,Extract, so the FeatureServer is the endpoint whose"
            " publisher intent to be extracted is explicit. The whole layer is taken on every"
            " pass rather than the newest month, because reporting_period is a rolling"
            " ~13-month window and a restatement inside it is invisible to a newest-month"
            " filter."
        ),
        "evidence_url": LAYER_URL,
        "code_ref": "src/glasswell/ingest/nm_c115b.py",
    },
    {
        "rule_id": "cr_nm_c115b_walk_order_1",
        "source_id": "nm_c115b_upstream",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["id", "reporting_period", "waste_type"],
        "spec": {
            "order_by": "id ASC, reporting_period ASC, waste_type ASC",
            "rejected_order": "OBJECTID ASC",
            "reason": "view_backed_layer_assigns_objectid_per_query",
            "tripwire": {
                "reason_code": "duplicate_row",
                "note": "a repeated identity key inside one harvest means the walk order"
                " stopped being total, not that the regulator filed twice",
            },
            "measured_2026_08_22": {
                "objectid_max": 71447,
                "row_count": 71447,
                "adjacent_2000_row_pages_overlapping_under_objectid": 52,
                "adjacent_2000_row_pages_overlapping_under_this_order": 0,
                "duplicate_keys_in_the_2026_08_21_objectid_snapshot": 5309,
            },
        },
        "rule": "Walk the layer ordered by (id, reporting_period, waste_type) — never by"
        " OBJECTID.",
        "rationale": (
            "The layer is view-backed: max(OBJECTID) equals the row count exactly and the same"
            " three rows answered with OBJECTIDs 67199/59784/62372 and then 59844/61928/67791"
            " seconds apart, so OBJECTID is assigned per query and is not an identity."
            " resultOffset re-runs the query for every page, so an OBJECTID-ordered walk"
            " silently re-reads and skips rows while count_before, count_after and"
            " features_written all reconcile: two adjacent 2,000-row pages shared 52 rows under"
            " OBJECTID ASC and none under this order, and the 2026-08-21 preservation snapshot"
            " taken that way carries 5,309 duplicated identity keys that are pagination"
            " artifacts rather than upstream data. (id, reporting_period, waste_type) is a total"
            " order, verified on a 521-row unpaginated slice where id is unique. The"
            " duplicate_row quarantine is the standing tripwire if that ever stops holding."
        ),
        "evidence_url": LAYER_URL,
        "code_ref": "src/glasswell/ingest/nm_c115b.py",
    },
    {
        "rule_id": "cr_nm_c115b_api10_1",
        "source_id": "nm_c115b_upstream",
        "stage": "parse",
        "rule_kind": "key_composite",
        "applies_to_fields": ["id"],
        "spec": {
            "module_function": "glasswell.ingest.nm_c115b:api10_from_dashed",
            "version": "1",
            "source_cols": ["id"],
            "target_col": "api10",
            "source_form": "SS-CCC-NNNNN",
            "target_form": "SSCCCNNNNN",
            "reason_code": "key_incomplete",
        },
        "rule": "Normalise the dashed id (30-015-03890) to the undashed API-10 (3001503890) that"
        " is the identity spine; an id that is not exactly 2-3-5 digits is held, never padded or"
        " truncated into one.",
        "rationale": (
            "C-115B is the only NM source in the register that ships the API number dashed, and"
            " the spine holds API-10 undashed, so every join from this source crosses this"
            " mapping — which makes it a row rather than a strip() somewhere in a parser. All"
            " 71,440 ids in the 2026-08-21 snapshot match 2-3-5 exactly, so the strictness costs"
            " nothing today and is the point on the day it does: stripping non-digits from a"
            " 14-character API-14 would silently key a wellbore onto its well, and zero-padding"
            " a short id would build a syntactically perfect API-10 for a well that does not"
            " exist (the failure D1-P3 measured on the RRC county plot points). Refusal to key"
            " is key_incomplete, the code migration 021 added for exactly this exit."
        ),
        "evidence_url": LAYER_URL,
        "code_ref": "src/glasswell/ingest/nm_c115b.py",
    },
    {
        "rule_id": "cr_nm_c115b_waste_vocab_1",
        "source_id": "nm_c115b_upstream",
        "stage": "parse",
        "rule_kind": "vocab_map",
        "applies_to_fields": ["waste_type"],
        "spec": {
            "mapping_table": "nm_waste_type_map",
            "key_col": "waste_type_raw",
            "value_col": "waste_type_canonical",
            "source_field": "waste_type",
            "unmapped_action": "quarantine",
            "reason_code": "unknown_vocab",
            "measured_2026_08_21": {"F": 5195, "V": 66245, "other": 0},
        },
        "rule": "Map waste_type F to flared and V to vented; any other code is quarantined"
        " rather than guessed.",
        "rationale": (
            "F and V are the only values the layer carries — 5,195 and 66,245 across all 71,440"
            " rows of the 2026-08-21 snapshot, with no third code and no nulls. The OCD"
            " publishes no codebook for the field, so the reading is stated here where a reader"
            " can check it rather than left implicit in a dictionary literal. The distinction is"
            " the whole value of the source: flared gas was burned and vented gas was released"
            " unburned, and a rollup that adds them without saying so answers a question nobody"
            " asked. Volumes under this vocabulary are reported waste, never production and"
            " never a reserve."
        ),
        "evidence_url": LAYER_URL,
        "code_ref": "src/glasswell/ingest/nm_c115b.py",
    },
    {
        "rule_id": "cr_nm_c115b_datum_1",
        "source_id": "nm_c115b_upstream",
        "stage": "parse",
        "rule_kind": "datum_transform",
        "applies_to_fields": ["geom"],
        "spec": {
            "source_epsg": 4269,
            "target_epsg": 4326,
            "detect": {"service_sr_wkid": 4269},
        },
        "rule": "Transform the NAD83 well points to EPSG:4326 before they reach storage.",
        "rationale": (
            "The layer's own spatialReference is wkid 4269 (NAD83), read from the layer JSON on"
            " every fetch and recorded on the manifest. Storage is always 4326 and the transform"
            " is recorded as a derivation even though the shift is sub-metre: no coordinate"
            " reaches storage untransformed and unrecorded (same rule as cr_nd_datum_1 and"
            " cr_blm_plss_datum_1)."
        ),
        "evidence_url": LAYER_URL,
    },
)

_INSERT_SOURCE = """
insert into lineage.sources (source_id, name, jurisdiction, license_note, redistributable)
values (%(source_id)s, %(name)s, %(jurisdiction)s, %(license_note)s, %(redistributable)s)
on conflict do nothing
"""

_INSERT_WASTE_TYPE = """
insert into lineage.nm_waste_type_map (waste_type_raw, waste_type_canonical)
values (%(waste_type_raw)s, %(waste_type_canonical)s)
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


def seed_sources_c115b(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_SOURCE, C115B_SOURCES)
    return len(C115B_SOURCES)


def seed_nm_waste_types(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_WASTE_TYPE, WASTE_TYPE_ROWS)
        cursor.execute("select count(*) from lineage.nm_waste_type_map")
        return int(cursor.fetchone()[0])


def seed_conformance_c115b(connection: psycopg.Connection) -> int:
    """Rule ids are immutable: a change is a new row with supersedes_rule_id (SB-07 §6.2)."""
    seed_sources_c115b(connection)
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_RULE, [_row(rule) for rule in C115B_RULES])
        cursor.execute(
            "select count(*) from lineage.conformance_rules"
            " where rule_id like 'cr\\_nm\\_c115b\\_%'"
        )
        return int(cursor.fetchone()[0])
