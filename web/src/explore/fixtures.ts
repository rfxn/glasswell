// Recorded from the tracked `tests/support/serve_branch.py` harness by
// `scripts/record-explorer-fixtures.py`. Request ids are normalized because they are volatile
// D3 envelope metadata; every other value is the locally served branch response.
//
//   GW_PORT=8130 GW_KEY_FILE=/tmp/gw-serve/owner.key make serve-branch
//   GW_BASE=http://127.0.0.1:8130 GW_KEY_FILE=/tmp/gw-serve/owner.key \
//     .venv/bin/python scripts/record-explorer-fixtures.py
//
// The owner key travels only in the request header and the recorder refuses to write it.

export { productionEnvelope } from "../test/fixtures.ts";

/** `GET /v1/wells?limit=8` — list_wells. */
export const wellsEnvelope = {
  "data": [
    {
      "api10": "3305300001",
      "confidential_flag": false,
      "county_code_at_permit": "053",
      "effective_from": "2026-08-01",
      "geometry_provenance": [],
      "land_unit_label": "151N-101W-11",
      "links": {
        "production": "/v1/wells/3305300001/production",
        "self": "/v1/wells/3305300001"
      },
      "operator_name_reported": "HESS",
      "spud_date": "2019-05-27",
      "status_canonical": "active",
      "well_name": "EXPLORER 1H"
    },
    {
      "api10": "3305300002",
      "confidential_flag": false,
      "county_code_at_permit": "053",
      "effective_from": "2026-08-01",
      "geometry_provenance": [],
      "land_unit_label": "151N-101W-11",
      "links": {
        "production": "/v1/wells/3305300002/production",
        "self": "/v1/wells/3305300002"
      },
      "operator_name_reported": "CONTINENTAL RESOURCES, INC",
      "spud_date": "2019-05-27",
      "status_canonical": "plugged",
      "well_name": "EXPLORER 2H"
    },
    {
      "api10": "3305300003",
      "confidential_flag": false,
      "county_code_at_permit": "053",
      "effective_from": "2026-08-01",
      "geometry_provenance": [],
      "land_unit_label": "151N-101W-11",
      "links": {
        "production": "/v1/wells/3305300003/production",
        "self": "/v1/wells/3305300003"
      },
      "operator_name_reported": "HESS",
      "spud_date": "2019-05-27",
      "status_canonical": "active",
      "well_name": "EXPLORER 3H"
    },
    {
      "api10": "3305300004",
      "confidential_flag": false,
      "county_code_at_permit": "053",
      "effective_from": "2026-08-01",
      "geometry_provenance": [],
      "land_unit_label": "151N-101W-11",
      "links": {
        "production": "/v1/wells/3305300004/production",
        "self": "/v1/wells/3305300004"
      },
      "operator_name_reported": "CONTINENTAL RESOURCES, INC",
      "spud_date": "2019-05-27",
      "status_canonical": "plugged",
      "well_name": "EXPLORER 4H"
    },
    {
      "api10": "3305300005",
      "confidential_flag": false,
      "county_code_at_permit": "053",
      "effective_from": "2026-08-01",
      "geometry_provenance": [],
      "land_unit_label": "151N-101W-11",
      "links": {
        "production": "/v1/wells/3305300005/production",
        "self": "/v1/wells/3305300005"
      },
      "operator_name_reported": "HESS",
      "spud_date": "2019-05-27",
      "status_canonical": "active",
      "well_name": "EXPLORER 5H"
    },
    {
      "api10": "3305300006",
      "confidential_flag": false,
      "county_code_at_permit": "053",
      "effective_from": "2026-08-01",
      "geometry_provenance": [],
      "land_unit_label": "151N-101W-11",
      "links": {
        "production": "/v1/wells/3305300006/production",
        "self": "/v1/wells/3305300006"
      },
      "operator_name_reported": "CONTINENTAL RESOURCES, INC",
      "spud_date": "2019-05-27",
      "status_canonical": "plugged",
      "well_name": "EXPLORER 6H"
    },
    {
      "api10": "3305302532",
      "confidential_flag": false,
      "county_code_at_permit": "053",
      "effective_from": "2026-08-01",
      "geometry_provenance": [],
      "land_unit_label": "151N-101W-11",
      "links": {
        "production": "/v1/wells/3305302532/production",
        "self": "/v1/wells/3305302532"
      },
      "operator_name_reported": "DEVON ENERGY WILLISTON, L.L.C",
      "spud_date": "2019-05-27",
      "status_canonical": "active",
      "well_name": "BIRDBEAR DUPEROW 1H"
    },
    {
      "api10": "3305310451",
      "confidential_flag": false,
      "county_code_at_permit": "053",
      "effective_from": "2026-08-01",
      "geometry_provenance": [
        "lateral"
      ],
      "land_unit_label": "151N-101W-11",
      "links": {
        "production": "/v1/wells/3305310451/production",
        "self": "/v1/wells/3305310451"
      },
      "operator_name_reported": "DEVON ENERGY WILLISTON, L.L.C",
      "spud_date": "2019-05-27",
      "status_canonical": "active",
      "well_name": "BILL 14-23 1H"
    }
  ],
  "links": {
    "explain": null,
    "next": null,
    "self": "/v1/wells"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": null,
    "request_id": "00000000000000000000000000",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/quarantine?limit=10` — list_quarantine. */
export const quarantineEnvelope = {
  "data": [
    {
      "first_seen_at": "2026-08-01T05:59:11+00:00",
      "first_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "last_seen_at": "2026-08-01T05:59:11+00:00",
      "last_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "notes": null,
      "occurrence_count": 74,
      "quarantine_id": "qr_01explorer0059",
      "reason_code": "key_collision",
      "release_derivation_id": null,
      "released_at": null,
      "released_by_rule_id": null,
      "row_fingerprint": "fp_explorer_0059",
      "rule_id": "cr_nd_stream_vocab_1",
      "source_id": "nd_gis_wells",
      "stage": "parse",
      "staging_table": "staging.nd_mpr_oil",
      "state": "accepted_loss"
    },
    {
      "first_seen_at": "2026-08-01T05:58:11+00:00",
      "first_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "last_seen_at": "2026-08-01T05:58:11+00:00",
      "last_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "notes": null,
      "occurrence_count": 67,
      "quarantine_id": "qr_01explorer0058",
      "reason_code": "datum_undetermined",
      "release_derivation_id": null,
      "released_at": null,
      "released_by_rule_id": null,
      "row_fingerprint": "fp_explorer_0058",
      "rule_id": "cr_nd_stream_vocab_1",
      "source_id": "nd_mpr_xlsx",
      "stage": "validate",
      "staging_table": "staging.nd_mpr_oil",
      "state": "released"
    },
    {
      "first_seen_at": "2026-08-01T05:57:11+00:00",
      "first_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "last_seen_at": "2026-08-01T05:57:11+00:00",
      "last_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "notes": null,
      "occurrence_count": 60,
      "quarantine_id": "qr_01explorer0057",
      "reason_code": "impossible_volume",
      "release_derivation_id": null,
      "released_at": null,
      "released_by_rule_id": null,
      "row_fingerprint": "fp_explorer_0057",
      "rule_id": "cr_nd_stream_vocab_1",
      "source_id": "nd_gis_wells",
      "stage": "conform",
      "staging_table": "staging.nd_mpr_oil",
      "state": "open"
    },
    {
      "first_seen_at": "2026-08-01T05:56:11+00:00",
      "first_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "last_seen_at": "2026-08-01T05:56:11+00:00",
      "last_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "notes": null,
      "occurrence_count": 53,
      "quarantine_id": "qr_01explorer0056",
      "reason_code": "unknown_vocab",
      "release_derivation_id": null,
      "released_at": null,
      "released_by_rule_id": null,
      "row_fingerprint": "fp_explorer_0056",
      "rule_id": "cr_nd_stream_vocab_1",
      "source_id": "nd_mpr_xlsx",
      "stage": "parse",
      "staging_table": "staging.nd_mpr_oil",
      "state": "open"
    },
    {
      "first_seen_at": "2026-08-01T05:55:11+00:00",
      "first_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "last_seen_at": "2026-08-01T05:55:11+00:00",
      "last_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "notes": null,
      "occurrence_count": 46,
      "quarantine_id": "qr_01explorer0055",
      "reason_code": "key_collision",
      "release_derivation_id": null,
      "released_at": null,
      "released_by_rule_id": null,
      "row_fingerprint": "fp_explorer_0055",
      "rule_id": "cr_nd_stream_vocab_1",
      "source_id": "nd_gis_wells",
      "stage": "validate",
      "staging_table": "staging.nd_mpr_oil",
      "state": "open"
    },
    {
      "first_seen_at": "2026-08-01T05:54:11+00:00",
      "first_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "last_seen_at": "2026-08-01T05:54:11+00:00",
      "last_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "notes": null,
      "occurrence_count": 39,
      "quarantine_id": "qr_01explorer0054",
      "reason_code": "datum_undetermined",
      "release_derivation_id": null,
      "released_at": null,
      "released_by_rule_id": null,
      "row_fingerprint": "fp_explorer_0054",
      "rule_id": "cr_nd_stream_vocab_1",
      "source_id": "nd_mpr_xlsx",
      "stage": "conform",
      "staging_table": "staging.nd_mpr_oil",
      "state": "accepted_loss"
    },
    {
      "first_seen_at": "2026-08-01T05:53:11+00:00",
      "first_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "last_seen_at": "2026-08-01T05:53:11+00:00",
      "last_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "notes": null,
      "occurrence_count": 32,
      "quarantine_id": "qr_01explorer0053",
      "reason_code": "impossible_volume",
      "release_derivation_id": null,
      "released_at": null,
      "released_by_rule_id": null,
      "row_fingerprint": "fp_explorer_0053",
      "rule_id": "cr_nd_stream_vocab_1",
      "source_id": "nd_gis_wells",
      "stage": "parse",
      "staging_table": "staging.nd_mpr_oil",
      "state": "released"
    },
    {
      "first_seen_at": "2026-08-01T05:52:11+00:00",
      "first_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "last_seen_at": "2026-08-01T05:52:11+00:00",
      "last_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "notes": null,
      "occurrence_count": 25,
      "quarantine_id": "qr_01explorer0052",
      "reason_code": "unknown_vocab",
      "release_derivation_id": null,
      "released_at": null,
      "released_by_rule_id": null,
      "row_fingerprint": "fp_explorer_0052",
      "rule_id": "cr_nd_stream_vocab_1",
      "source_id": "nd_mpr_xlsx",
      "stage": "validate",
      "staging_table": "staging.nd_mpr_oil",
      "state": "open"
    },
    {
      "first_seen_at": "2026-08-01T05:51:11+00:00",
      "first_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "last_seen_at": "2026-08-01T05:51:11+00:00",
      "last_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "notes": null,
      "occurrence_count": 18,
      "quarantine_id": "qr_01explorer0051",
      "reason_code": "key_collision",
      "release_derivation_id": null,
      "released_at": null,
      "released_by_rule_id": null,
      "row_fingerprint": "fp_explorer_0051",
      "rule_id": "cr_nd_stream_vocab_1",
      "source_id": "nd_gis_wells",
      "stage": "conform",
      "staging_table": "staging.nd_mpr_oil",
      "state": "open"
    },
    {
      "first_seen_at": "2026-08-01T05:50:11+00:00",
      "first_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "last_seen_at": "2026-08-01T05:50:11+00:00",
      "last_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "notes": null,
      "occurrence_count": 11,
      "quarantine_id": "qr_01explorer0050",
      "reason_code": "datum_undetermined",
      "release_derivation_id": null,
      "released_at": null,
      "released_by_rule_id": null,
      "row_fingerprint": "fp_explorer_0050",
      "rule_id": "cr_nd_stream_vocab_1",
      "source_id": "nd_mpr_xlsx",
      "stage": "parse",
      "staging_table": "staging.nd_mpr_oil",
      "state": "open"
    }
  ],
  "links": {
    "explain": null,
    "next": "/v1/quarantine?limit=10&cursor=eyJrIjoiMjAyNi0wOC0wMVQwNTo1MDoxMSswMDowMCIsInEiOiI0NDEzNmZhMyIsInQiOiJxcl8wMWV4cGxvcmVyMDA1MCIsInYiOm51bGx9",
    "self": "/v1/quarantine"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {
      "/reason_code": "gt_quarantine",
      "/state": "gt_quarantine_state"
    },
    "next_cursor": "eyJrIjoiMjAyNi0wOC0wMVQwNTo1MDoxMSswMDowMCIsInEiOiI0NDEzNmZhMyIsInQiOiJxcl8wMWV4cGxvcmVyMDA1MCIsInYiOm51bGx9",
    "request_id": "00000000000000000000000000",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/conformance?limit=6` — list_conformance_rules. */
export const conformanceEnvelope = {
  "data": [
    {
      "applies_to_fields": [
        "geom",
        "distance_m",
        "distance_epsg"
      ],
      "code_ref": "glasswell.marts.neighbors:refresh_neighbors",
      "effective_from": "2026-08-27",
      "effective_to": null,
      "evidence_sha256": null,
      "evidence_url": "https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Horizontals_Line.zip",
      "published_vintage": "2026-08-27",
      "rationale": "The Williston extent crosses the 102W UTM boundary, so one projected zone cannot measure every pair defensibly. Candidate discovery and final measurement are separated: the equal-area candidate CRS receives a measured two-percent guard, while the shortest-line midpoint selects the local UTM zone used for the admitted scalar distance. All promoted lateral components participate and geometry keys close deterministic ties, preventing a convenient component or zone from being substituted at serve time.",
      "rule": "Discover ND lateral pairs in padded EPSG:5070, then persist the minimum distance measured in pair-local UTM 13N or 14N through 26,400 feet.",
      "rule_family": "cr_nd_neighbor_distance",
      "rule_id": "cr_nd_neighbor_distance_1",
      "rule_kind": "code_ref",
      "source_id": "nd_gis_horizontals_line",
      "spec": {
        "candidate_epsg": 5070,
        "candidate_pad_headroom_ft_min": "181.2",
        "candidate_radius_pad": "1.02",
        "candidate_to_final_distance_ratio_max": "1.013136",
        "candidate_validation_cases": 12672,
        "candidate_validation_domain": {
          "latitude": [
            "45.90",
            "49.05"
          ],
          "longitude": [
            "-104.15",
            "-96.50"
          ],
          "source": "scripts/basemap-regions/nd.geojson"
        },
        "component_policy": "minimum_over_all_promoted_lateral_component_pairs",
        "contract_note": "EPSG:5070 discovers a padded candidate set only; the persisted distance is measured in pair-local UTM 13N or 14N and admitted only through 26,400 feet",
        "max_radius_ft": 26400,
        "measurement_epsg": [
          32613,
          32614
        ],
        "module_function": "glasswell.marts.neighbors:refresh_neighbors",
        "storage_epsg": 4326,
        "tie_break": [
          "distance_m",
          "subject_geom_key",
          "neighbor_geom_key"
        ],
        "version": "1",
        "zone_boundary_longitude": "-102",
        "zone_selection": "candidate_crs_shortest_line_midpoint"
      },
      "stage": "conform",
      "supersedes_rule_id": null
    },
    {
      "applies_to_fields": [
        "pool_reported",
        "formation",
        "formation_group"
      ],
      "code_ref": "glasswell.marts.neighbors:refresh_neighbors",
      "effective_from": "2026-08-27",
      "effective_to": null,
      "evidence_sha256": null,
      "evidence_url": "https://www.dmr.nd.gov/oilgas/mpr/2026_03.xlsx",
      "published_vintage": "2026-08-27",
      "rationale": "The endpoint offers an exact formation filter, so two exact formations cannot be collapsed merely because they share a broader peer group. Missing aliases and sub-threshold aliases are availability states, not geological conflicts. Legacy unscoped aliases are excluded so another source namespace cannot silently supply this mart's context; the selected source-scoped alias rows are content-hashed into the derivation identity.",
      "rule": "Classify neighbour formation from the complete earliest-month ND pool set using source-scoped reviewed aliases only; never infer an unavailable mapping.",
      "rule_family": "cr_nd_neighbor_context",
      "rule_id": "cr_nd_neighbor_context_1",
      "rule_kind": "code_ref",
      "source_id": "nd_mpr_xlsx",
      "spec": {
        "alias_scope": "source_scoped_only_no_legacy_fallback",
        "conflict_policy": "distinct_exact_formation_or_group_is_conflict",
        "contract_note": "every earliest-month pool must have one source-scoped alias at confidence 0.800 or higher; exact formations and groups must each collapse to one",
        "minimum_confidence": "0.800",
        "module_function": "glasswell.marts.neighbors:refresh_neighbors",
        "pool_policy": "earliest_nonblank_source_month_set",
        "unavailable_policy": "never_infer",
        "version": "1"
      },
      "stage": "join",
      "supersedes_rule_id": null
    },
    {
      "applies_to_fields": [
        "pool",
        "formation_group"
      ],
      "code_ref": null,
      "effective_from": "2026-08-26",
      "effective_to": null,
      "evidence_sha256": null,
      "evidence_url": "https://www.dmr.nd.gov/oilgas/mpr/2026_03.xlsx",
      "published_vintage": "2026-08-26",
      "rationale": "The MPR pool vocabulary is a source label, not a model peer group. The reviewed crosswalk preserves exact formations, keeps Three Forks distinct from Bakken, and sends ambiguous composites or sub-threshold targets to __other__ rather than asserting geology the source does not support. The row-by-row mapping remains queryable and append-only so a later geological review is a new knowledge vintage, not a code edit.",
      "rule": "Resolve each reported ND MPR pool through the vintaged formation alias table.",
      "rule_family": "cr_nd_formation_group",
      "rule_id": "cr_nd_formation_group_1",
      "rule_kind": "alias_join",
      "source_id": "nd_mpr_xlsx",
      "spec": {
        "alias_table": "formation_aliases",
        "key_cols": [
          "formation_raw"
        ],
        "min_confidence": "0.800",
        "reason_code": "alias_unresolved",
        "target_col": "formation_group",
        "unmatched_action": "quarantine"
      },
      "stage": "join",
      "supersedes_rule_id": null
    },
    {
      "applies_to_fields": [
        "state_code",
        "basin"
      ],
      "code_ref": "glasswell.ingest.nd_gis:_promote_wells",
      "effective_from": "2026-08-26",
      "effective_to": null,
      "evidence_sha256": null,
      "evidence_url": "https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Wells.zip",
      "published_vintage": "2026-08-26",
      "rationale": "The v0 ND product and its fv1.0 feature partition are defined at the Williston modeling-basin scope, while OGD_Wells is the statewide identity source and does not publish a basin attribute. The assignment is therefore an explicit modeling conformance rule, not an inferred source field. Keeping it in the registry makes the state-to-model-scope decision visible and replaceable if a future basin boundary source supports a narrower spatial classification.",
      "rule": "Assign North Dakota OGD wells to the v0 Williston modeling basin.",
      "rule_family": "cr_nd_basin",
      "rule_id": "cr_nd_basin_1",
      "rule_kind": "code_ref",
      "source_id": "nd_gis_wells",
      "spec": {
        "basin": "williston",
        "contract_note": "_promote_wells writes basin=williston on each ND well revision; a future boundary source must supersede this rule rather than silently narrow it",
        "module_function": "glasswell.ingest.nd_gis:_promote_wells",
        "scope": "v0 North Dakota modeling basin",
        "state_code": "33",
        "version": "1"
      },
      "stage": "conform",
      "supersedes_rule_id": null
    },
    {
      "applies_to_fields": [
        "DisclosureList_1.csv"
      ],
      "code_ref": null,
      "effective_from": "2026-08-26",
      "effective_to": null,
      "evidence_sha256": null,
      "evidence_url": "https://www.fracfocusdata.org/digitaldownload/FracFocusCSV.zip",
      "published_vintage": "2026-08-26",
      "rationale": "The 440 MB archive expands beyond 3 GiB. Streaming one member keeps the source artifact immutable and avoids materialising all members together; every member is still decompressed once for its manifest SHA-256 inventory.",
      "rule": "Stream DisclosureList_1.csv from the archive and retain source text in staging.",
      "rule_family": "cr_ff_disclosure_parse",
      "rule_id": "cr_ff_disclosure_parse_1",
      "rule_kind": "parse_directive",
      "source_id": "fracfocus_csv",
      "spec": {
        "all_columns": "text",
        "encoding": "utf-8-sig",
        "member": "DisclosureList_1.csv",
        "member_stream": true,
        "timestamp_formats": [
          "%m/%d/%Y %I:%M:%S %p",
          "%m/%d/%Y",
          "%Y-%m-%d"
        ]
      },
      "stage": "parse",
      "supersedes_rule_id": null
    },
    {
      "applies_to_fields": [
        "JobStartDate",
        "JobEndDate",
        "completion_date"
      ],
      "code_ref": "glasswell.ingest.fracfocus:materialize_nd_readiness",
      "effective_from": "2026-08-26",
      "effective_to": null,
      "evidence_sha256": null,
      "evidence_url": "https://www.fracfocusdata.org/digitaldownload/FracFocusCSV.zip",
      "published_vintage": "2026-08-26",
      "rationale": "FracFocus's bundled data dictionary defines JobEndDate as the date the hydraulic fracturing job was completed, excluding teardown. It is a completion event, not a spud or production proxy. The earliest event is selected because later disclosures can be refractures; every disclosure remains in canonical so that choice is inspectable. ND's free OGD well extract has no completion date, while the regulator's completion-bearing Well Index is subscription-only.",
      "rule": "Use the earliest valid FracFocus hydraulic-fracturing JobEndDate as the ND pre-production completion anchor.",
      "rule_family": "cr_ff_completion_anchor",
      "rule_id": "cr_ff_completion_anchor_1",
      "rule_kind": "code_ref",
      "source_id": "fracfocus_csv",
      "spec": {
        "anchor_kind": "hydraulic_frac_job_end",
        "contract_note": "materialize_nd_readiness selects min(JobEndDate) per API-10 from current disclosure observations and never coalesces spud or production dates",
        "forbidden_proxies": [
          "spud_date",
          "first_production_month"
        ],
        "module_function": "glasswell.ingest.fracfocus:materialize_nd_readiness",
        "reject_if": [
          "job_end_missing",
          "job_end_before_job_start"
        ],
        "source_field": "JobEndDate",
        "version": "1",
        "well_selection": "earliest_valid_job_end_per_api10"
      },
      "stage": "conform",
      "supersedes_rule_id": null
    }
  ],
  "links": {
    "explain": null,
    "next": "/v1/conformance?limit=6&cursor=eyJrIjoiMjAyNi0wOC0yNiIsInEiOiI0NDEzNmZhMyIsInQiOiJjcl9mZl9jb21wbGV0aW9uX2FuY2hvcl8xIiwidiI6IjIwMjYtMDgtMjgifQ",
    "self": "/v1/conformance"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": "2026-08-28"
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": "eyJrIjoiMjAyNi0wOC0yNiIsInEiOiI0NDEzNmZhMyIsInQiOiJjcl9mZl9jb21wbGV0aW9uX2FuY2hvcl8xIiwidiI6IjIwMjYtMDgtMjgifQ",
    "request_id": "00000000000000000000000000",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/manifests?limit=6` — list_manifests. */
export const manifestsEnvelope = {
  "data": [
    {
      "acquisition_method": "https_get",
      "acquisition_url": "https://example.invalid/2026_06.xlsx",
      "bytes": 64,
      "decompressed_inventory": [],
      "fetch_derivation_id": null,
      "fetch_vintage": "2026-08-01",
      "fetched_at": "2026-08-01T05:02:11+00:00",
      "license_note": null,
      "manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "media_type": null,
      "redistributable": false,
      "sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "source_id": "nd_mpr_xlsx",
      "source_key": "2026_06.xlsx",
      "storage_uri": "/data/raw/nd_mpr_xlsx/2026_06.xlsx",
      "superseded_by": null,
      "supersedes": null
    },
    {
      "acquisition_method": "https_get",
      "acquisition_url": "https://example.invalid/OGD_Wells.zip",
      "bytes": 64,
      "decompressed_inventory": [],
      "fetch_derivation_id": null,
      "fetch_vintage": "2026-08-01",
      "fetched_at": "2026-08-01T05:02:11+00:00",
      "license_note": null,
      "manifest_id": "man_dddddddddddddddddddddddddddddddd",
      "media_type": null,
      "redistributable": false,
      "sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
      "source_id": "nd_gis_wells",
      "source_key": "OGD_Wells.zip",
      "storage_uri": "/data/raw/nd_gis_wells/OGD_Wells.zip",
      "superseded_by": null,
      "supersedes": null
    }
  ],
  "links": {
    "explain": null,
    "next": null,
    "self": "/v1/manifests"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": null,
    "request_id": "00000000000000000000000000",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/derivations?limit=6` — list_derivations. */
export const derivationsEnvelope = {
  "data": [
    {
      "code_version": "git:0000test",
      "created_at": "2026-08-01T05:00:00+00:00",
      "created_vintage": "2026-08-01",
      "derivation_id": "drv_tcfhfxnptv2oucdmjtzq",
      "determinism_class": "D1",
      "model_id": null,
      "operation": "canonical.promote",
      "output_dataset": "canonical.well_spatial",
      "output_rows": 2,
      "output_store": "postgis",
      "recipe_id": null,
      "status": "ok"
    },
    {
      "code_version": "git:0000test",
      "created_at": "2026-08-01T05:00:00+00:00",
      "created_vintage": "2026-08-01",
      "derivation_id": "drv_obqajdni25f25zmxcz7a",
      "determinism_class": "D1",
      "model_id": null,
      "operation": "canonical.promote",
      "output_dataset": "canonical.production_monthly",
      "output_rows": 18,
      "output_store": "postgres",
      "recipe_id": null,
      "status": "ok"
    }
  ],
  "links": {
    "explain": null,
    "next": null,
    "self": "/v1/derivations"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": null,
    "request_id": "00000000000000000000000000",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/vintages` — list_vintages. */
export const vintagesEnvelope = {
  "data": [
    {
      "_lineage": {
        "restatement_summary": "drv_obqajdni25f25zmxcz7a",
        "rows_appended": "drv_obqajdni25f25zmxcz7a",
        "rows_examined": "drv_obqajdni25f25zmxcz7a"
      },
      "manifest_ids": [
        "man_dddddddddddddddddddddddddddddddd"
      ],
      "months_touched": [
        "2026-01-01",
        "2026-02-01",
        "2026-03-01",
        "2026-04-01",
        "2026-05-01",
        "2026-06-01"
      ],
      "opened_at": "2026-08-01T05:02:11+00:00",
      "promotion_derivation_id": "drv_obqajdni25f25zmxcz7a",
      "restatement_summary": {},
      "rows_appended": 119001,
      "rows_examined": 120001,
      "source_id": "nd_gis_wells",
      "vintage_date": "2026-08-01",
      "vintage_id": "vin_nd_gis_wells_2026-08-01"
    },
    {
      "_lineage": {
        "restatement_summary": "drv_obqajdni25f25zmxcz7a",
        "rows_appended": "drv_obqajdni25f25zmxcz7a",
        "rows_examined": "drv_obqajdni25f25zmxcz7a"
      },
      "manifest_ids": [
        "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
      ],
      "months_touched": [
        "2026-01-01",
        "2026-02-01",
        "2026-03-01",
        "2026-04-01",
        "2026-05-01",
        "2026-06-01"
      ],
      "opened_at": "2026-08-01T05:02:11+00:00",
      "promotion_derivation_id": "drv_obqajdni25f25zmxcz7a",
      "restatement_summary": {},
      "rows_appended": 119000,
      "rows_examined": 120000,
      "source_id": "nd_mpr_xlsx",
      "vintage_date": "2026-08-01",
      "vintage_id": "vin_nd_mpr_xlsx_2026-08-01"
    }
  ],
  "links": {
    "explain": "/v1/explain?h=drv_obqajdni25f25zmxcz7a&depth=full",
    "next": null,
    "self": "/v1/vintages"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": null,
    "request_id": "00000000000000000000000000",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/glossary?limit=6` — list_glossary_terms. */
export const glossaryEnvelope = {
  "data": [
    {
      "aliases": [
        "API-10",
        "API-12",
        "API-14",
        "API number"
      ],
      "domain_tags": [
        "identity",
        "data-model"
      ],
      "highlightable": true,
      "short_definition": "The American Petroleum Institute well number; API-10 is glasswell's identity spine.",
      "term": "API-10 / API-12 / API-14",
      "term_id": "gt_api_10_api_12_api_14"
    },
    {
      "aliases": [
        "Allocation",
        "Allocated"
      ],
      "domain_tags": [
        "production",
        "data-model"
      ],
      "highlightable": true,
      "short_definition": "Estimating well-level volumes from a lease-level report by splitting the lease total across its wells.",
      "term": "Allocation / allocation v0",
      "term_id": "gt_allocation_allocation_v0"
    },
    {
      "aliases": [],
      "domain_tags": [
        "modeling"
      ],
      "highlightable": false,
      "short_definition": "A well near another in feature space - rock, design, location - rather than in physical space.",
      "term": "Analog",
      "term_id": "gt_analog"
    },
    {
      "aliases": [],
      "domain_tags": [
        "lineage",
        "governance"
      ],
      "highlightable": true,
      "short_definition": "The system's single append-only event log: restatements, promotions, model publications and key uses are events in it.",
      "term": "Audit stream",
      "term_id": "gt_audit_stream"
    },
    {
      "aliases": [],
      "domain_tags": [
        "modeling"
      ],
      "highlightable": false,
      "short_definition": "The P10-P90 interval around a forecast or type curve.",
      "term": "Band",
      "term_id": "gt_band"
    },
    {
      "aliases": [
        "Petroleum basin"
      ],
      "domain_tags": [
        "geology",
        "data-model"
      ],
      "highlightable": true,
      "short_definition": "A named geologic region registered for a source namespace.",
      "term": "Basin",
      "term_id": "gt_basin"
    }
  ],
  "links": {
    "explain": null,
    "next": "/v1/glossary?limit=6&cursor=eyJrIjoiQmFzaW4iLCJxIjoiNDQxMzZmYTMiLCJ0IjoiZ3RfYmFzaW4iLCJ2IjpudWxsfQ",
    "self": "/v1/glossary"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": "eyJrIjoiQmFzaW4iLCJxIjoiNDQxMzZmYTMiLCJ0IjoiZ3RfYmFzaW4iLCJ2IjpudWxsfQ",
    "request_id": "00000000000000000000000000",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/health` — get_health. */
export const healthEnvelope = {
  "data": {
    "degraded_sources": [
      "nd_gis_wells",
      "nd_mpr_xlsx"
    ],
    "pending_sources": [
      "blm_plss_sections",
      "blm_plss_townships",
      "fracfocus_csv",
      "nd_gis_directionals",
      "nd_gis_horizontals_line",
      "nd_gis_spacing_units",
      "nm_c115b_upstream",
      "nm_ocd_ogrid",
      "nm_ocd_pod",
      "nm_ocd_podwc",
      "nm_ocd_pool",
      "nm_ocd_property",
      "nm_ocd_spacingunit",
      "nm_ocd_wchistory",
      "nm_ocd_wcproduction",
      "nm_ocd_wellhistory",
      "proj_grid_nad27",
      "tx_gis_wells_county",
      "tx_wellbore_ewa_csv"
    ],
    "sources": [
      {
        "cadence": "Every 35 days",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "BLM national CadNSDI PLSS sections / first division (NAD83 service, layer 2)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "blm_plss_sections",
        "state": "pending"
      },
      {
        "cadence": "Every 35 days",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "BLM national CadNSDI PLSS townships (NAD83 service, layer 1)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "blm_plss_townships",
        "state": "pending"
      },
      {
        "cadence": "Every 8 days",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "FracFocus bulk CSV disclosure archive",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "fracfocus_csv",
        "state": "pending"
      },
      {
        "cadence": "Every 35 days",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "ND DMR GIS directional survey stations (OGD_Directionals)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "nd_gis_directionals",
        "state": "pending"
      },
      {
        "cadence": "Every 8 days",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "ND DMR GIS lateral centrelines (OGD_Horizontals_Line)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "nd_gis_horizontals_line",
        "state": "pending"
      },
      {
        "cadence": "Every 8 days",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "ND DMR GIS drilling spacing units (OGD_DrillingSpacingUnits)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "nd_gis_spacing_units",
        "state": "pending"
      },
      {
        "cadence": "Every 8 days",
        "declared_vintage": "2026-08-01",
        "freshness_reason": "The artifact is older than the expected poll interval and no durable attempt can prove that the source was checked unchanged.",
        "last_attempt_at": null,
        "last_manifest_id": "man_dddddddddddddddddddddddddddddddd",
        "last_outcome": null,
        "manifest_count": 1,
        "name": "nd gis wells",
        "next_expected_poll": null,
        "retrieval_vintage": "2026-08-01",
        "source_id": "nd_gis_wells",
        "state": "stale"
      },
      {
        "cadence": "Every 8 days",
        "declared_vintage": "2026-08-01",
        "freshness_reason": "The artifact is older than the expected poll interval and no durable attempt can prove that the source was checked unchanged.",
        "last_attempt_at": null,
        "last_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        "last_outcome": null,
        "manifest_count": 1,
        "name": "nd mpr xlsx",
        "next_expected_poll": null,
        "retrieval_vintage": "2026-08-01",
        "source_id": "nd_mpr_xlsx",
        "state": "stale"
      },
      {
        "cadence": "Every 35 days",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "NM OCD C-115B natural gas waste, upstream by well API (FeatureServer layer 0)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "nm_c115b_upstream",
        "state": "pending"
      },
      {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "NM OCD operator registry (ogrid)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "nm_ocd_ogrid",
        "state": "pending"
      },
      {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "NM OCD pooled development units (pod)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "nm_ocd_pod",
        "state": "pending"
      },
      {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "NM OCD POD to well-completion crosswalk (podwc)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "nm_ocd_podwc",
        "state": "pending"
      },
      {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "NM OCD pool registry (pool)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "nm_ocd_pool",
        "state": "pending"
      },
      {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "NM OCD properties (property)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "nm_ocd_property",
        "state": "pending"
      },
      {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "NM OCD spacing units (spacingunit)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "nm_ocd_spacingunit",
        "state": "pending"
      },
      {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "NM OCD well-completion history (wchistory)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "nm_ocd_wchistory",
        "state": "pending"
      },
      {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "NM OCD well-completion monthly volumes (wcproduction)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "nm_ocd_wcproduction",
        "state": "pending"
      },
      {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "NM OCD well header history (wellhistory)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "nm_ocd_wellhistory",
        "state": "pending"
      },
      {
        "cadence": "When the dependency pin changes",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "NOAA NADCON grid used by the NAD27 transform (us_noaa_conus.tif)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "proj_grid_nad27",
        "state": "pending"
      },
      {
        "cadence": "Every 8 days",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "TX RRC GIS well layers by county (well###.zip)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "tx_gis_wells_county",
        "state": "pending"
      },
      {
        "cadence": "Every 35 days",
        "declared_vintage": null,
        "freshness_reason": "No durable poll attempt or registered artifact exists yet.",
        "last_attempt_at": null,
        "last_manifest_id": null,
        "last_outcome": null,
        "manifest_count": 0,
        "name": "TX RRC Wellbore Query export (OG_WELLBORE_EWA_Report.csv)",
        "next_expected_poll": null,
        "retrieval_vintage": null,
        "source_id": "tx_wellbore_ewa_csv",
        "state": "pending"
      }
    ],
    "state": "degraded",
    "stores": {
      "postgres": "ok"
    }
  },
  "links": {
    "explain": null,
    "next": null,
    "self": "/v1/health"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": null,
    "request_id": "00000000000000000000000000",
    "source_freshness": {
      "blm_plss_sections": {
        "cadence": "Every 35 days",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "blm_plss_townships": {
        "cadence": "Every 35 days",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "fracfocus_csv": {
        "cadence": "Every 8 days",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "nd_gis_directionals": {
        "cadence": "Every 35 days",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "nd_gis_horizontals_line": {
        "cadence": "Every 8 days",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "nd_gis_spacing_units": {
        "cadence": "Every 8 days",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "nd_gis_wells": {
        "cadence": "Every 8 days",
        "declared_vintage": "2026-08-01",
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "The artifact is older than the expected poll interval and no durable attempt can prove that the source was checked unchanged.",
        "retrieval_vintage": "2026-08-01",
        "state": "stale"
      },
      "nd_mpr_xlsx": {
        "cadence": "Every 8 days",
        "declared_vintage": "2026-08-01",
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "The artifact is older than the expected poll interval and no durable attempt can prove that the source was checked unchanged.",
        "retrieval_vintage": "2026-08-01",
        "state": "stale"
      },
      "nm_c115b_upstream": {
        "cadence": "Every 35 days",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "nm_ocd_ogrid": {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "nm_ocd_pod": {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "nm_ocd_podwc": {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "nm_ocd_pool": {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "nm_ocd_property": {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "nm_ocd_spacingunit": {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "nm_ocd_wchistory": {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "nm_ocd_wcproduction": {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "nm_ocd_wellhistory": {
        "cadence": "Every 36 hours",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "proj_grid_nad27": {
        "cadence": "When the dependency pin changes",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "tx_gis_wells_county": {
        "cadence": "Every 8 days",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      },
      "tx_wellbore_ewa_csv": {
        "cadence": "Every 35 days",
        "declared_vintage": null,
        "last_attempt_at": null,
        "last_outcome": null,
        "next_expected_poll": null,
        "reason": "No durable poll attempt or registered artifact exists yet.",
        "retrieval_vintage": null,
        "state": "pending"
      }
    },
    "warnings": []
  }
};

/** `GET /v1` — get_service_index. */
export const serviceIndexEnvelope = {
  "data": {
    "api_version": "v1",
    "deprecations": [],
    "error_codes": [
      {
        "code": "unauthenticated",
        "emitted_by_this_slice": true,
        "status": 403,
        "title": "Not authenticated",
        "type": "/v1/errors/unauthenticated"
      },
      {
        "code": "forbidden",
        "emitted_by_this_slice": true,
        "status": 403,
        "title": "Forbidden",
        "type": "/v1/errors/forbidden"
      },
      {
        "code": "key_required",
        "emitted_by_this_slice": true,
        "status": 403,
        "title": "API key required",
        "type": "/v1/errors/key_required"
      },
      {
        "code": "key_revoked",
        "emitted_by_this_slice": true,
        "status": 403,
        "title": "API key revoked",
        "type": "/v1/errors/key_revoked"
      },
      {
        "code": "jwks_unavailable",
        "emitted_by_this_slice": false,
        "status": 503,
        "title": "Identity keys unavailable",
        "type": "/v1/errors/jwks_unavailable"
      },
      {
        "code": "not_found",
        "emitted_by_this_slice": true,
        "status": 404,
        "title": "Not found",
        "type": "/v1/errors/not_found"
      },
      {
        "code": "validation_failed",
        "emitted_by_this_slice": true,
        "status": 422,
        "title": "Request validation failed",
        "type": "/v1/errors/validation_failed"
      },
      {
        "code": "cursor_malformed",
        "emitted_by_this_slice": true,
        "status": 422,
        "title": "Cursor malformed",
        "type": "/v1/errors/cursor_malformed"
      },
      {
        "code": "cursor_query_mismatch",
        "emitted_by_this_slice": true,
        "status": 422,
        "title": "Cursor does not match this query",
        "type": "/v1/errors/cursor_query_mismatch"
      },
      {
        "code": "as_of_out_of_range",
        "emitted_by_this_slice": true,
        "status": 422,
        "title": "as_of precedes the captured history",
        "type": "/v1/errors/as_of_out_of_range"
      },
      {
        "code": "selector_ambiguous",
        "emitted_by_this_slice": true,
        "status": 422,
        "title": "Handle selector is ambiguous",
        "type": "/v1/errors/selector_ambiguous"
      },
      {
        "code": "lineage_unresolved",
        "emitted_by_this_slice": true,
        "status": 404,
        "title": "Lineage could not be resolved",
        "type": "/v1/errors/lineage_unresolved"
      },
      {
        "code": "explain_on_dry_run",
        "emitted_by_this_slice": true,
        "status": 422,
        "title": "explain cannot be combined with dry_run",
        "type": "/v1/errors/explain_on_dry_run"
      },
      {
        "code": "result_cap_exceeded",
        "emitted_by_this_slice": false,
        "status": 422,
        "title": "Result cap exceeded",
        "type": "/v1/errors/result_cap_exceeded"
      },
      {
        "code": "unregistered_artifact",
        "emitted_by_this_slice": false,
        "status": 409,
        "title": "Artifact is not registered",
        "type": "/v1/errors/unregistered_artifact"
      },
      {
        "code": "model_not_promoted",
        "emitted_by_this_slice": false,
        "status": 409,
        "title": "Model is not promoted",
        "type": "/v1/errors/model_not_promoted"
      },
      {
        "code": "idempotency_conflict",
        "emitted_by_this_slice": false,
        "status": 409,
        "title": "Idempotency key conflict",
        "type": "/v1/errors/idempotency_conflict"
      },
      {
        "code": "idempotency_in_progress",
        "emitted_by_this_slice": false,
        "status": 409,
        "title": "Idempotent request in progress",
        "type": "/v1/errors/idempotency_in_progress"
      },
      {
        "code": "job_not_cancellable",
        "emitted_by_this_slice": false,
        "status": 409,
        "title": "Job is not cancellable",
        "type": "/v1/errors/job_not_cancellable"
      },
      {
        "code": "tile_token_invalid",
        "emitted_by_this_slice": false,
        "status": 403,
        "title": "Tile token invalid",
        "type": "/v1/errors/tile_token_invalid"
      },
      {
        "code": "tile_layer_not_entitled",
        "emitted_by_this_slice": false,
        "status": 403,
        "title": "Tile layer not entitled",
        "type": "/v1/errors/tile_layer_not_entitled"
      },
      {
        "code": "rate_limited",
        "emitted_by_this_slice": false,
        "status": 429,
        "title": "Rate limited",
        "type": "/v1/errors/rate_limited"
      },
      {
        "code": "payload_too_large",
        "emitted_by_this_slice": false,
        "status": 413,
        "title": "Payload too large",
        "type": "/v1/errors/payload_too_large"
      },
      {
        "code": "unsupported_format",
        "emitted_by_this_slice": true,
        "status": 415,
        "title": "Unsupported format",
        "type": "/v1/errors/unsupported_format"
      },
      {
        "code": "upstream_tile_error",
        "emitted_by_this_slice": true,
        "status": 502,
        "title": "Tile upstream failed",
        "type": "/v1/errors/upstream_tile_error"
      },
      {
        "code": "service_degraded",
        "emitted_by_this_slice": true,
        "status": 503,
        "title": "Service degraded",
        "type": "/v1/errors/service_degraded"
      }
    ],
    "published_vintages": [
      {
        "promotion_derivation_id": "drv_obqajdni25f25zmxcz7a",
        "rows_appended": 119001,
        "rows_examined": 120001,
        "source_id": "nd_gis_wells",
        "vintage_date": "2026-08-01"
      },
      {
        "promotion_derivation_id": "drv_obqajdni25f25zmxcz7a",
        "rows_appended": 119000,
        "rows_examined": 120000,
        "source_id": "nd_mpr_xlsx",
        "vintage_date": "2026-08-01"
      }
    ]
  },
  "links": {
    "conformance": "/v1/conformance",
    "derivations": "/v1/derivations",
    "explain": "/v1/explain?h=",
    "formations": "/v1/formations",
    "glossary": "/v1/glossary",
    "glossary_index": "/v1/glossary/index",
    "health": "/v1/health",
    "manifests": "/v1/manifests",
    "next": null,
    "openapi": "/openapi.json",
    "quarantine": "/v1/quarantine",
    "self": "/v1",
    "status": "/v1/status",
    "tiles": "/v1/tiles",
    "well_neighbors": "/v1/wells/{api10}/neighbors",
    "wells": "/v1/wells"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": null,
    "request_id": "00000000000000000000000000",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/quarantine/summary` — get_quarantine_summary. */
export const quarantineSummaryEnvelope = {
  "data": {
    "group_by": "reason_code",
    "groups": [
      {
        "count": 24,
        "key": "impossible_volume",
        "share": 0.258065
      },
      {
        "count": 24,
        "key": "unknown_vocab",
        "share": 0.258065
      },
      {
        "count": 23,
        "key": "datum_undetermined",
        "share": 0.247312
      },
      {
        "count": 22,
        "key": "key_collision",
        "share": 0.236559
      }
    ],
    "total": 93
  },
  "links": {
    "explain": null,
    "next": null,
    "self": "/v1/quarantine/summary"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {
      "/groups": "gt_quarantine"
    },
    "next_cursor": null,
    "request_id": "00000000000000000000000000",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/wells/3305302532/production/pools` — get_well_production_pools. */
export const pooledProductionEnvelope = {
  "data": {
    "_basis": {
      "pools.0.series.oil_bbl": "oil+condensate",
      "pools.0.series.water_bbl": "water",
      "pools.1.series.oil_bbl": "oil+condensate",
      "pools.1.series.water_bbl": "water"
    },
    "_lineage": {
      "pools.0.series.gas_mcf.0": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=gas_mcf&pm=2026-01",
      "pools.0.series.gas_mcf.1": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=gas_mcf&pm=2026-02",
      "pools.0.series.gas_mcf.2": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=gas_mcf&pm=2026-03",
      "pools.0.series.gas_mcf.3": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=gas_mcf&pm=2026-04",
      "pools.0.series.gas_mcf.4": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=gas_mcf&pm=2026-05",
      "pools.0.series.gas_mcf.5": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=gas_mcf&pm=2026-06",
      "pools.0.series.oil_bbl.0": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=oil_bbl&pm=2026-01",
      "pools.0.series.oil_bbl.1": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=oil_bbl&pm=2026-02",
      "pools.0.series.oil_bbl.2": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=oil_bbl&pm=2026-03",
      "pools.0.series.oil_bbl.3": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=oil_bbl&pm=2026-04",
      "pools.0.series.oil_bbl.4": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=oil_bbl&pm=2026-05",
      "pools.0.series.oil_bbl.5": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=oil_bbl&pm=2026-06",
      "pools.0.series.water_bbl.0": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=water_bbl&pm=2026-01",
      "pools.0.series.water_bbl.1": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=water_bbl&pm=2026-02",
      "pools.0.series.water_bbl.2": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=water_bbl&pm=2026-03",
      "pools.0.series.water_bbl.3": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=water_bbl&pm=2026-04",
      "pools.0.series.water_bbl.4": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=water_bbl&pm=2026-05",
      "pools.0.series.water_bbl.5": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:BIRDBEAR&col=water_bbl&pm=2026-06",
      "pools.1.series.gas_mcf.0": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=gas_mcf&pm=2026-01",
      "pools.1.series.gas_mcf.1": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=gas_mcf&pm=2026-02",
      "pools.1.series.gas_mcf.2": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=gas_mcf&pm=2026-03",
      "pools.1.series.gas_mcf.3": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=gas_mcf&pm=2026-04",
      "pools.1.series.gas_mcf.4": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=gas_mcf&pm=2026-05",
      "pools.1.series.gas_mcf.5": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=gas_mcf&pm=2026-06",
      "pools.1.series.oil_bbl.0": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=oil_bbl&pm=2026-01",
      "pools.1.series.oil_bbl.1": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=oil_bbl&pm=2026-02",
      "pools.1.series.oil_bbl.2": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=oil_bbl&pm=2026-03",
      "pools.1.series.oil_bbl.3": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=oil_bbl&pm=2026-04",
      "pools.1.series.oil_bbl.4": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=oil_bbl&pm=2026-05",
      "pools.1.series.oil_bbl.5": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=oil_bbl&pm=2026-06",
      "pools.1.series.water_bbl.0": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=water_bbl&pm=2026-01",
      "pools.1.series.water_bbl.1": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=water_bbl&pm=2026-02",
      "pools.1.series.water_bbl.2": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=water_bbl&pm=2026-03",
      "pools.1.series.water_bbl.3": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=water_bbl&pm=2026-04",
      "pools.1.series.water_bbl.4": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=water_bbl&pm=2026-05",
      "pools.1.series.water_bbl.5": "drv_obqajdni25f25zmxcz7a#entity_key=3305302532:DUPEROW&col=water_bbl&pm=2026-06"
    },
    "_units": {
      "pools.0.series.gas_mcf": "mcf",
      "pools.0.series.oil_bbl": "bbl",
      "pools.0.series.water_bbl": "bbl",
      "pools.1.series.gas_mcf": "mcf",
      "pools.1.series.oil_bbl": "bbl",
      "pools.1.series.water_bbl": "bbl"
    },
    "api10": "3305302532",
    "granularity": "well_observed",
    "pools": [
      {
        "entity_key": "3305302532:BIRDBEAR",
        "series": {
          "gas_mcf": [
            "600.000",
            "1200.000",
            "1800.000",
            "2400.000",
            "3000.000",
            "3600.000"
          ],
          "gas_mcf_null_semantics": [
            "reported",
            "reported",
            "reported",
            "reported",
            "reported",
            "reported"
          ],
          "gas_mcf_report_vintage": [
            "2026-07-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01"
          ],
          "oil_bbl": [
            "300.000",
            "600.000",
            "900.000",
            "1200.000",
            "1500.000",
            "1800.000"
          ],
          "oil_bbl_null_semantics": [
            "reported",
            "reported",
            "reported",
            "reported",
            "reported",
            "reported"
          ],
          "oil_bbl_report_vintage": [
            "2026-07-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01"
          ],
          "pm": [
            "2026-01",
            "2026-02",
            "2026-03",
            "2026-04",
            "2026-05",
            "2026-06"
          ],
          "water_bbl": [
            "900.000",
            "1800.000",
            "2700.000",
            "3600.000",
            "4500.000",
            "5400.000"
          ],
          "water_bbl_null_semantics": [
            "reported",
            "reported",
            "no_report",
            "reported",
            "reported",
            "reported"
          ],
          "water_bbl_report_vintage": [
            "2026-07-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01"
          ]
        },
        "streams": [
          "oil",
          "gas",
          "water"
        ],
        "well_completion_pool": "BIRDBEAR"
      },
      {
        "entity_key": "3305302532:DUPEROW",
        "series": {
          "gas_mcf": [
            "7170.000",
            "14340.000",
            "21510.000",
            "28680.000",
            "35850.000",
            "43020.000"
          ],
          "gas_mcf_null_semantics": [
            "reported",
            "reported",
            "reported",
            "reported",
            "reported",
            "reported"
          ],
          "gas_mcf_report_vintage": [
            "2026-07-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01"
          ],
          "oil_bbl": [
            "3585.000",
            "7170.000",
            "10755.000",
            "14340.000",
            "17925.000",
            "21510.000"
          ],
          "oil_bbl_null_semantics": [
            "reported",
            "reported",
            "reported",
            "reported",
            "reported",
            "reported"
          ],
          "oil_bbl_report_vintage": [
            "2026-07-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01"
          ],
          "pm": [
            "2026-01",
            "2026-02",
            "2026-03",
            "2026-04",
            "2026-05",
            "2026-06"
          ],
          "water_bbl": [
            "10755.000",
            "21510.000",
            "32265.000",
            "43020.000",
            "53775.000",
            "64530.000"
          ],
          "water_bbl_null_semantics": [
            "reported",
            "reported",
            "no_report",
            "reported",
            "reported",
            "reported"
          ],
          "water_bbl_report_vintage": [
            "2026-07-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01",
            "2026-08-01"
          ]
        },
        "streams": [
          "oil",
          "gas",
          "water"
        ],
        "well_completion_pool": "DUPEROW"
      }
    ],
    "reporting_level": "well_completion_pool"
  },
  "links": {
    "aggregation_rule": "/v1/conformance/cr_nd_pool_rollup_1",
    "explain": "/v1/explain?h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Doil_bbl%26pm%3D2026-01&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Doil_bbl%26pm%3D2026-02&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Doil_bbl%26pm%3D2026-03&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Doil_bbl%26pm%3D2026-04&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Doil_bbl%26pm%3D2026-05&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Doil_bbl%26pm%3D2026-06&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Dgas_mcf%26pm%3D2026-01&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Dgas_mcf%26pm%3D2026-02&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Dgas_mcf%26pm%3D2026-03&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Dgas_mcf%26pm%3D2026-04&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Dgas_mcf%26pm%3D2026-05&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Dgas_mcf%26pm%3D2026-06&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Dwater_bbl%26pm%3D2026-01&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Dwater_bbl%26pm%3D2026-02&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Dwater_bbl%26pm%3D2026-03&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Dwater_bbl%26pm%3D2026-04&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Dwater_bbl%26pm%3D2026-05&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ABIRDBEAR%26col%3Dwater_bbl%26pm%3D2026-06&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ADUPEROW%26col%3Doil_bbl%26pm%3D2026-01&h=drv_obqajdni25f25zmxcz7a%23entity_key%3D3305302532%3ADUPEROW%26col%3Doil_bbl%26pm%3D2026-02&depth=full",
    "next": null,
    "production": "/v1/wells/3305302532/production",
    "self": "/v1/wells/3305302532/production/pools",
    "well": "/v1/wells/3305302532"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": "2026-08-01"
    },
    "deprecations": [],
    "labels": {
      "/api10": "gt_api_10_api_12_api_14",
      "/granularity": "gt_granularity",
      "/pools/0/series/gas_mcf": "gt_stream",
      "/pools/0/series/gas_mcf_null_semantics": "gt_withheld",
      "/pools/0/series/gas_mcf_report_vintage": "gt_report_vintage",
      "/pools/0/series/oil_bbl": "gt_liquids_policy",
      "/pools/0/series/oil_bbl_null_semantics": "gt_withheld",
      "/pools/0/series/oil_bbl_report_vintage": "gt_report_vintage",
      "/pools/0/series/water_bbl": "gt_stream",
      "/pools/0/series/water_bbl_null_semantics": "gt_withheld",
      "/pools/0/series/water_bbl_report_vintage": "gt_report_vintage",
      "/pools/0/well_completion_pool": "gt_pool",
      "/pools/1/series/gas_mcf": "gt_stream",
      "/pools/1/series/gas_mcf_null_semantics": "gt_withheld",
      "/pools/1/series/gas_mcf_report_vintage": "gt_report_vintage",
      "/pools/1/series/oil_bbl": "gt_liquids_policy",
      "/pools/1/series/oil_bbl_null_semantics": "gt_withheld",
      "/pools/1/series/oil_bbl_report_vintage": "gt_report_vintage",
      "/pools/1/series/water_bbl": "gt_stream",
      "/pools/1/series/water_bbl_null_semantics": "gt_withheld",
      "/pools/1/series/water_bbl_report_vintage": "gt_report_vintage",
      "/pools/1/well_completion_pool": "gt_pool"
    },
    "next_cursor": null,
    "request_id": "00000000000000000000000000",
    "source_freshness": {
      "nd_mpr_xlsx": {
        "declared_vintage": "2026-08-01",
        "retrieval_vintage": "2026-08-01",
        "state": "current"
      }
    },
    "warnings": []
  }
};

/** `GET /v1/wells/3305300003/production` — get_well_production. */
export const emptyProductionEnvelope = {
  "data": {
    "api10": "3305300003",
    "granularity": "well_observed",
    "reporting_level": "well",
    "series": {
      "pm": []
    },
    "source_id": null,
    "streams": []
  },
  "links": {
    "explain": null,
    "next": null,
    "self": "/v1/wells/3305300003/production",
    "well": "/v1/wells/3305300003"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {
      "/api10": "gt_api_10_api_12_api_14",
      "/granularity": "gt_granularity"
    },
    "next_cursor": null,
    "request_id": "00000000000000000000000000",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/quarantine?limit=2` — list_quarantine. */
export const pagedQuarantineEnvelope = {
  "data": [
    {
      "first_seen_at": "2026-08-01T05:59:11+00:00",
      "first_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "last_seen_at": "2026-08-01T05:59:11+00:00",
      "last_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "notes": null,
      "occurrence_count": 74,
      "quarantine_id": "qr_01explorer0059",
      "reason_code": "key_collision",
      "release_derivation_id": null,
      "released_at": null,
      "released_by_rule_id": null,
      "row_fingerprint": "fp_explorer_0059",
      "rule_id": "cr_nd_stream_vocab_1",
      "source_id": "nd_gis_wells",
      "stage": "parse",
      "staging_table": "staging.nd_mpr_oil",
      "state": "accepted_loss"
    },
    {
      "first_seen_at": "2026-08-01T05:58:11+00:00",
      "first_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "last_seen_at": "2026-08-01T05:58:11+00:00",
      "last_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "notes": null,
      "occurrence_count": 67,
      "quarantine_id": "qr_01explorer0058",
      "reason_code": "datum_undetermined",
      "release_derivation_id": null,
      "released_at": null,
      "released_by_rule_id": null,
      "row_fingerprint": "fp_explorer_0058",
      "rule_id": "cr_nd_stream_vocab_1",
      "source_id": "nd_mpr_xlsx",
      "stage": "validate",
      "staging_table": "staging.nd_mpr_oil",
      "state": "released"
    }
  ],
  "links": {
    "explain": null,
    "next": "/v1/quarantine?limit=2&cursor=eyJrIjoiMjAyNi0wOC0wMVQwNTo1ODoxMSswMDowMCIsInEiOiI0NDEzNmZhMyIsInQiOiJxcl8wMWV4cGxvcmVyMDA1OCIsInYiOm51bGx9",
    "self": "/v1/quarantine"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {
      "/reason_code": "gt_quarantine",
      "/state": "gt_quarantine_state"
    },
    "next_cursor": "eyJrIjoiMjAyNi0wOC0wMVQwNTo1ODoxMSswMDowMCIsInEiOiI0NDEzNmZhMyIsInQiOiJxcl8wMWV4cGxvcmVyMDA1OCIsInYiOm51bGx9",
    "request_id": "00000000000000000000000000",
    "source_freshness": {},
    "warnings": []
  }
};
