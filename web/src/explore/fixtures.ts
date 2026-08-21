// Recorded from a locally-served build of this branch on 2026-08-21, not hand-written from
// the router source, so a shape drift in the API fails a web test rather than the owner's
// first click. `work-output/explorer-c7-serve.py` stands the stack up; this file is written by
// `work-output/explorer-c7-record.py`, which is how it is refreshed rather than edited.
//
//   curl -H "X-Glasswell-Key: $KEY" .../v1/wells?limit=8
//   curl -H "X-Glasswell-Key: $KEY" .../v1/quarantine?limit=10   (and ?limit=2, for the cursor)
//   curl -H "X-Glasswell-Key: $KEY" .../v1/wells/3305302532/production/pools
//   …one per exported constant below, each named for the operation it came from.
//
// The deployed instance is not the source: it serves the document that was deployed, and the
// dataset extension exists only on this branch. The owner key travels in the header and
// appears in no body here — the recorder asserts that before writing.
//
// The per-well production envelope is NOT recorded again: `web/src/test/fixtures.ts` already
// holds one and that file is read-only to SB-08, so C7 imports it rather than forking it.
// The pooled well files in two pools, because the contract fixture's well files in one and a
// `pools: []` response cannot exercise a pooled row (C2 MUST-KNOW P4).

export { productionEnvelope } from "../test/fixtures.ts";

/** `GET /v1/wells?limit=8` — list_wells. */
export const wellsEnvelope = {
  "data": [
    {
      "api10": "3305300001",
      "confidential_flag": false,
      "county_code_at_permit": "053",
      "effective_from": "2026-08-01",
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
    "request_id": "01M0HWF7XVX34JS0MCBKJ4KJH0",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/quarantine?limit=10` — list_quarantine. */
export const quarantineEnvelope = {
  "data": [
    {
      "first_seen_at": "2026-08-01T05:02:11+00:00",
      "first_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "last_seen_at": "2026-08-01T05:02:11+00:00",
      "last_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "notes": null,
      "occurrence_count": 2,
      "quarantine_id": "qr_01contract0003",
      "reason_code": "unknown_vocab",
      "release_derivation_id": null,
      "released_at": null,
      "released_by_rule_id": null,
      "row_fingerprint": "fp_contract_0003",
      "rule_id": "cr_nd_status_vocab_1",
      "source_id": "nd_gis_wells",
      "stage": "conform",
      "staging_table": "staging.nd_gis_wells",
      "state": "released"
    },
    {
      "first_seen_at": "2026-08-01T05:02:11+00:00",
      "first_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "last_seen_at": "2026-08-01T05:02:11+00:00",
      "last_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "notes": null,
      "occurrence_count": 1,
      "quarantine_id": "qr_01contract0002",
      "reason_code": "impossible_volume",
      "release_derivation_id": null,
      "released_at": null,
      "released_by_rule_id": null,
      "row_fingerprint": "fp_contract_0002",
      "rule_id": "cr_nd_volume_range_1",
      "source_id": "nd_mpr_xlsx",
      "stage": "validate",
      "staging_table": "staging.nd_mpr_oil",
      "state": "open"
    },
    {
      "first_seen_at": "2026-08-01T05:02:11+00:00",
      "first_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "last_seen_at": "2026-08-01T05:02:11+00:00",
      "last_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "notes": null,
      "occurrence_count": 3,
      "quarantine_id": "qr_01contract0001",
      "reason_code": "unknown_vocab",
      "release_derivation_id": null,
      "released_at": null,
      "released_by_rule_id": null,
      "row_fingerprint": "fp_contract_0001",
      "rule_id": "cr_nd_stream_vocab_1",
      "source_id": "nd_mpr_xlsx",
      "stage": "conform",
      "staging_table": "staging.nd_mpr_oil",
      "state": "open"
    }
  ],
  "links": {
    "explain": null,
    "next": null,
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
      "/state": "gt_quarantine"
    },
    "next_cursor": null,
    "request_id": "01M0HWF7YAR5K0GCX6PA75GGPY",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/conformance?limit=6` — list_conformance_rules. */
export const conformanceEnvelope = {
  "data": [
    {
      "applies_to_fields": [
        "all"
      ],
      "code_ref": null,
      "effective_from": "2026-08-21",
      "effective_to": null,
      "evidence_sha256": null,
      "evidence_url": "https://www.emnrd.nm.gov/ocd/ocd-data/ftp-server/",
      "rationale": "Eleven values were measured over all 48.1M records, and two of them are traps: a lowercase p on 7 rows and a single space on 42,366. An exact-match vocabulary seeded from a hand-copied distinct-value list that lost either would quarantine 42,373 rows as unknown_status, which is why the domain is recorded here with its counts. What the letters mean is a different question, and the OCD publishes no codebook mapping them to a well status: lineage.nm_status_map is therefore left empty rather than filled with a plausible guess, because a canonical status invented for an undocumented single-letter code is a mapping that exists only in the head of whoever guessed it, which is what R8 exists to prevent. When the codebook is in evidence the map is populated and a vocab_map row supersedes this declaration.",
      "rule": "The C-115 well-completion status code is staged verbatim and promoted to no canonical status until its codebook is in evidence.",
      "rule_family": "cr_nm_wcproduction_status_vocab",
      "rule_id": "cr_nm_wcproduction_status_vocab_1",
      "rule_kind": "parse_directive",
      "source_id": "nm_ocd_wcproduction",
      "spec": {
        "asserts_header": false,
        "counts": {
          " ": 42366,
          "A": 47439,
          "D": 15375,
          "F": 20557177,
          "G": 391371,
          "I": 97456,
          "L": 6,
          "P": 23532167,
          "S": 2686669,
          "T": 734301,
          "p": 7
        },
        "declares_fields": [
          "c115_wc_stat_cde"
        ],
        "domain": [
          "P",
          "F",
          "S",
          "T",
          "G",
          "I",
          "A",
          " ",
          "D",
          "p",
          "L"
        ],
        "promoted": false,
        "target_map": "nm_status_map"
      },
      "stage": "conform",
      "supersedes_rule_id": null
    },
    {
      "applies_to_fields": [
        "all"
      ],
      "code_ref": null,
      "effective_from": "2026-08-21",
      "effective_to": null,
      "evidence_sha256": null,
      "evidence_url": "https://www.emnrd.nm.gov/ocd/ocd-data/ftp-server/",
      "rationale": "DIR-2 makes the vintage a dimension rather than an overwrite, and migration 008's append-only trigger (008:29-31) makes a canonical UPDATE an error rather than a warning, so this rule states what the trigger enforces and what the promotion must therefore do. The trigger for an append is a value change and not the regulator's flag: the export re-publishes all 48.1M rows nightly, 34,812,326 of them carrying amend_ind N, so reading the flag as the signal would treat a re-publication as a statement that nothing changed. amend_ind is kept as evidence beside the appended row, and mod_dte is a promotion shortcut compared against the staged prior partition; neither enters value_hash (cr_nm_wcproduction_mod_dte_1). The vintage itself is glasswell's own stamp because the artifact is undated and overwritten in place upstream (cr_nm_wcproduction_undated_vintage_1).",
      "rule": "A restated NM month is appended under a new report vintage. Nothing in canonical is ever updated in place.",
      "rule_family": "cr_nm_wcproduction_restatement",
      "rule_id": "cr_nm_wcproduction_restatement_1",
      "rule_kind": "parse_directive",
      "source_id": "nm_ocd_wcproduction",
      "spec": {
        "amend_ind_role": "evidence",
        "asserts_header": false,
        "declares_fields": [
          "prod_amt",
          "amend_ind",
          "mod_dte"
        ],
        "detection": "value_hash change for the same entity_key, production_month and stream across report vintages",
        "in_place_update": "prohibited",
        "mod_dte_role": "promotion_shortcut",
        "on_change": "append_new_report_vintage",
        "vintage_rule_id": "cr_nm_wcproduction_undated_vintage_1"
      },
      "stage": "conform",
      "supersedes_rule_id": null
    },
    {
      "applies_to_fields": [
        "all"
      ],
      "code_ref": null,
      "effective_from": "2026-08-21",
      "effective_to": null,
      "evidence_sha256": null,
      "evidence_url": "https://www.emnrd.nm.gov/ocd/ocd-data/ftp-server/",
      "rationale": "prod_amt is never null and never blank across 48,104,334 records and 6,812,255 rows report zero, so NM's live distinction is reported against reported_zero and the absent states are defensive rather than observed. The vocabulary written here is the one migration 009's CHECK admits - reported, reported_zero, no_report, withheld. PLAN-NM P3.3 named withheld_confidential and not_applicable, which that CHECK rejects; D1 writes what the constraint admits and does not alter another track's constraint to fit its own rule (entry gate G6). A filter would delete the row that carries the absence, which is the distinction this rule exists to keep (\u00a73.0.3).",
      "rule": "Why a volume is absent is a fact with its own vocabulary; a reported zero is not an absence, and neither is ever collapsed into the other.",
      "rule_family": "cr_nm_wcproduction_null_semantics",
      "rule_id": "cr_nm_wcproduction_null_semantics_1",
      "rule_kind": "parse_directive",
      "source_id": "nm_ocd_wcproduction",
      "spec": {
        "asserts_header": false,
        "canonical_column": "null_semantics",
        "collapse": "never",
        "declares_fields": [
          "prod_amt"
        ],
        "measured": {
          "null_prod_amt": 0,
          "reported_zero": 6812255
        },
        "vocabulary": [
          "reported",
          "reported_zero",
          "no_report",
          "withheld"
        ]
      },
      "stage": "conform",
      "supersedes_rule_id": null
    },
    {
      "applies_to_fields": [
        "all"
      ],
      "code_ref": null,
      "effective_from": "2026-08-21",
      "effective_to": null,
      "evidence_sha256": null,
      "evidence_url": "https://www.emnrd.nm.gov/ocd/ocd-data/ftp-server/",
      "rationale": "T1-b asked whether NM has a condensate discriminator and assumed the answer was no, in which case NM would have carried stream = oil with liquids_policy = oil_plus_condensate, as ND does. The artifact answers otherwise: prd_knd_cde carries 'C ' on 3,398 rows, so for those months oil and condensate are two filings and adding them silently would restate the operator. Liquid without qualification means oil plus condensate in this product, which is exactly why the policy travels with the figure: an NM liquids rollup is the labelled sum of the oil and condensate streams, never an oil row quietly containing both. Where the operator filed no condensate row - every month after 1993 - the oil row is what was filed and nothing is added to it.",
      "rule": "NM reports condensate as its own stream, so an NM oil figure is oil as filed and any liquids figure that adds condensate to it says so.",
      "rule_family": "cr_nm_wcproduction_liquids",
      "rule_id": "cr_nm_wcproduction_liquids_1",
      "rule_kind": "parse_directive",
      "source_id": "nm_ocd_wcproduction",
      "spec": {
        "asserts_header": false,
        "condensate_months_observed": "1986-01 through 1993-12",
        "condensate_stream": "condensate",
        "declares_fields": [
          "prd_knd_cde",
          "prod_amt"
        ],
        "liquids_policy": "oil_and_condensate_reported_separately",
        "oil_includes_condensate": false
      },
      "stage": "conform",
      "supersedes_rule_id": null
    },
    {
      "applies_to_fields": [
        "all"
      ],
      "code_ref": null,
      "effective_from": "2026-08-21",
      "effective_to": null,
      "evidence_sha256": null,
      "evidence_url": "https://www.emnrd.nm.gov/ocd/ocd-data/",
      "rationale": "The disposition artifacts that carry it - othervolume, podvolume, podstorage and wcinjection, 738 MB combined - are deliberately not fetched, because the volume they hold attaches to a Property while this spine's grain is well completion x pool. Splitting a Property's flare volume across its completions would put an estimate into canonical, and DIR-3 keeps canonical at native granularity with estimates named as such elsewhere. The decision is a row rather than a note so that a reader asking for NM flaring finds the reason, and so that a later phase which does fetch the disposition tables supersedes a stated decision instead of discovering an unstated one.",
      "rule": "NM flaring is filed against a Property, not a well completion, so no NM flare volume is derived at the spine's grain and none is served.",
      "rule_family": "cr_nm_wcproduction_flare_property",
      "rule_id": "cr_nm_wcproduction_flare_property_1",
      "rule_kind": "parse_directive",
      "source_id": "nm_ocd_wcproduction",
      "spec": {
        "asserts_header": false,
        "declares_fields": [],
        "flare_reporting_grain": "property",
        "served": false,
        "sources_out_of_scope": [
          "othervolume",
          "podvolume",
          "podstorage",
          "wcinjection"
        ],
        "well_completion_flare_series": "not_derivable"
      },
      "stage": "conform",
      "supersedes_rule_id": null
    },
    {
      "applies_to_fields": [
        "all"
      ],
      "code_ref": null,
      "effective_from": "2026-08-21",
      "effective_to": null,
      "evidence_sha256": null,
      "evidence_url": "https://www.emnrd.nm.gov/ocd/ocd-data/ftp-server/",
      "rationale": "Measured identically on the XML side and off the staged Parquet: N 34,812,326, Y 13,280,514, then 1, 2, 4, 6, 9, 3, X and 7 across 11,494 rows. A boolean reading mis-classifies every one of those 11,494, and it is the reading a column named _ind invites. The eight numeric and X codes are undocumented - the OCD publishes no codebook for them - so nothing is promoted from this column and the raw value stays staged where a later phase holding a codebook can map it under a new rule row. Its part in change detection belongs to cr_nm_wcproduction_mod_dte_1: amend_ind is the regulator's evidence that a row was amended, not the trigger, because the trigger is a value change.",
      "rule": "amend_ind is a ten-value vocabulary carried verbatim into staging, promoted to no canonical column, and never read as a Y/N flag.",
      "rule_family": "cr_nm_wcproduction_amend_ind",
      "rule_id": "cr_nm_wcproduction_amend_ind_1",
      "rule_kind": "parse_directive",
      "source_id": "nm_ocd_wcproduction",
      "spec": {
        "asserts_header": false,
        "boolean_reading": "prohibited",
        "change_detection_rule_id": "cr_nm_wcproduction_mod_dte_1",
        "counts": {
          "1": 5959,
          "2": 5252,
          "3": 8,
          "4": 185,
          "6": 72,
          "7": 2,
          "9": 10,
          "N": 34812326,
          "X": 6,
          "Y": 13280514
        },
        "declares_fields": [
          "amend_ind"
        ],
        "domain": [
          "N",
          "Y",
          "1",
          "2",
          "3",
          "4",
          "6",
          "7",
          "9",
          "X"
        ],
        "promoted": false
      },
      "stage": "conform",
      "supersedes_rule_id": null
    }
  ],
  "links": {
    "explain": null,
    "next": "/v1/conformance?limit=6&cursor=eyJrIjoiMjAyNi0wOC0yMSIsInEiOiI0NDEzNmZhMyIsInQiOiJjcl9ubV93Y3Byb2R1Y3Rpb25fYW1lbmRfaW5kXzEiLCJ2IjpudWxsfQ",
    "self": "/v1/conformance"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": "eyJrIjoiMjAyNi0wOC0yMSIsInEiOiI0NDEzNmZhMyIsInQiOiJjcl9ubV93Y3Byb2R1Y3Rpb25fYW1lbmRfaW5kXzEiLCJ2IjpudWxsfQ",
    "request_id": "01M0HWF7YPR67APFWK9T4ER210",
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
    "request_id": "01M0HWF7Z2C1GAB6KJ0SEG16SY",
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
    "request_id": "01M0HWF7ZC441D31X2JS2AF4RA",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/vintages` — list_vintages. */
export const vintagesEnvelope = {
  "data": [
    {
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
    "explain": null,
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
    "request_id": "01M0HWF7ZPH60TX01FVTKN0ZFN",
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
        "Bitemporality"
      ],
      "domain_tags": [
        "lineage",
        "time",
        "data-model"
      ],
      "highlightable": true,
      "short_definition": "Carrying two time axes: when something happened (the production month) and when it was reported (the report vintage).",
      "term": "Bitemporal",
      "term_id": "gt_bitemporal"
    }
  ],
  "links": {
    "explain": null,
    "next": "/v1/glossary?limit=6&cursor=eyJrIjoiQml0ZW1wb3JhbCIsInEiOiI0NDEzNmZhMyIsInQiOiJndF9iaXRlbXBvcmFsIiwidiI6bnVsbH0",
    "self": "/v1/glossary"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": "eyJrIjoiQml0ZW1wb3JhbCIsInEiOiI0NDEzNmZhMyIsInQiOiJndF9iaXRlbXBvcmFsIiwidiI6bnVsbH0",
    "request_id": "01M0HWF8015C00WWTPJE0XAG4J",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/health` — get_health. */
export const healthEnvelope = {
  "data": {
    "degraded_sources": [
      "nd_gis_horizontals_line",
      "nd_gis_spacing_units",
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
        "declared_vintage": null,
        "last_manifest_id": null,
        "manifest_count": 0,
        "name": "ND DMR GIS lateral centrelines (OGD_Horizontals_Line)",
        "retrieval_vintage": null,
        "source_id": "nd_gis_horizontals_line",
        "state": "never_fetched"
      },
      {
        "declared_vintage": null,
        "last_manifest_id": null,
        "manifest_count": 0,
        "name": "ND DMR GIS drilling spacing units (OGD_DrillingSpacingUnits)",
        "retrieval_vintage": null,
        "source_id": "nd_gis_spacing_units",
        "state": "never_fetched"
      },
      {
        "declared_vintage": "2026-08-01",
        "last_manifest_id": "man_dddddddddddddddddddddddddddddddd",
        "manifest_count": 1,
        "name": "nd gis wells",
        "retrieval_vintage": "2026-08-01",
        "source_id": "nd_gis_wells",
        "state": "current"
      },
      {
        "declared_vintage": "2026-08-01",
        "last_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        "manifest_count": 1,
        "name": "nd mpr xlsx",
        "retrieval_vintage": "2026-08-01",
        "source_id": "nd_mpr_xlsx",
        "state": "current"
      },
      {
        "declared_vintage": null,
        "last_manifest_id": null,
        "manifest_count": 0,
        "name": "NM OCD operator registry (ogrid)",
        "retrieval_vintage": null,
        "source_id": "nm_ocd_ogrid",
        "state": "never_fetched"
      },
      {
        "declared_vintage": null,
        "last_manifest_id": null,
        "manifest_count": 0,
        "name": "NM OCD pooled development units (pod)",
        "retrieval_vintage": null,
        "source_id": "nm_ocd_pod",
        "state": "never_fetched"
      },
      {
        "declared_vintage": null,
        "last_manifest_id": null,
        "manifest_count": 0,
        "name": "NM OCD POD to well-completion crosswalk (podwc)",
        "retrieval_vintage": null,
        "source_id": "nm_ocd_podwc",
        "state": "never_fetched"
      },
      {
        "declared_vintage": null,
        "last_manifest_id": null,
        "manifest_count": 0,
        "name": "NM OCD pool registry (pool)",
        "retrieval_vintage": null,
        "source_id": "nm_ocd_pool",
        "state": "never_fetched"
      },
      {
        "declared_vintage": null,
        "last_manifest_id": null,
        "manifest_count": 0,
        "name": "NM OCD properties (property)",
        "retrieval_vintage": null,
        "source_id": "nm_ocd_property",
        "state": "never_fetched"
      },
      {
        "declared_vintage": null,
        "last_manifest_id": null,
        "manifest_count": 0,
        "name": "NM OCD spacing units (spacingunit)",
        "retrieval_vintage": null,
        "source_id": "nm_ocd_spacingunit",
        "state": "never_fetched"
      },
      {
        "declared_vintage": null,
        "last_manifest_id": null,
        "manifest_count": 0,
        "name": "NM OCD well-completion history (wchistory)",
        "retrieval_vintage": null,
        "source_id": "nm_ocd_wchistory",
        "state": "never_fetched"
      },
      {
        "declared_vintage": null,
        "last_manifest_id": null,
        "manifest_count": 0,
        "name": "NM OCD well-completion monthly volumes (wcproduction)",
        "retrieval_vintage": null,
        "source_id": "nm_ocd_wcproduction",
        "state": "never_fetched"
      },
      {
        "declared_vintage": null,
        "last_manifest_id": null,
        "manifest_count": 0,
        "name": "NM OCD well header history (wellhistory)",
        "retrieval_vintage": null,
        "source_id": "nm_ocd_wellhistory",
        "state": "never_fetched"
      },
      {
        "declared_vintage": null,
        "last_manifest_id": null,
        "manifest_count": 0,
        "name": "NOAA NADCON grid used by the NAD27 transform (us_noaa_conus.tif)",
        "retrieval_vintage": null,
        "source_id": "proj_grid_nad27",
        "state": "never_fetched"
      },
      {
        "declared_vintage": null,
        "last_manifest_id": null,
        "manifest_count": 0,
        "name": "TX RRC GIS well layers by county (well###.zip)",
        "retrieval_vintage": null,
        "source_id": "tx_gis_wells_county",
        "state": "never_fetched"
      },
      {
        "declared_vintage": null,
        "last_manifest_id": null,
        "manifest_count": 0,
        "name": "TX RRC Wellbore Query export (OG_WELLBORE_EWA_Report.csv)",
        "retrieval_vintage": null,
        "source_id": "tx_wellbore_ewa_csv",
        "state": "never_fetched"
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
    "request_id": "01M0HWF80BAKQCXT6C17XH8YYJ",
    "source_freshness": {
      "nd_gis_horizontals_line": {
        "declared_vintage": null,
        "retrieval_vintage": null,
        "state": "never_fetched"
      },
      "nd_gis_spacing_units": {
        "declared_vintage": null,
        "retrieval_vintage": null,
        "state": "never_fetched"
      },
      "nd_gis_wells": {
        "declared_vintage": "2026-08-01",
        "retrieval_vintage": "2026-08-01",
        "state": "current"
      },
      "nd_mpr_xlsx": {
        "declared_vintage": "2026-08-01",
        "retrieval_vintage": "2026-08-01",
        "state": "current"
      },
      "nm_ocd_ogrid": {
        "declared_vintage": null,
        "retrieval_vintage": null,
        "state": "never_fetched"
      },
      "nm_ocd_pod": {
        "declared_vintage": null,
        "retrieval_vintage": null,
        "state": "never_fetched"
      },
      "nm_ocd_podwc": {
        "declared_vintage": null,
        "retrieval_vintage": null,
        "state": "never_fetched"
      },
      "nm_ocd_pool": {
        "declared_vintage": null,
        "retrieval_vintage": null,
        "state": "never_fetched"
      },
      "nm_ocd_property": {
        "declared_vintage": null,
        "retrieval_vintage": null,
        "state": "never_fetched"
      },
      "nm_ocd_spacingunit": {
        "declared_vintage": null,
        "retrieval_vintage": null,
        "state": "never_fetched"
      },
      "nm_ocd_wchistory": {
        "declared_vintage": null,
        "retrieval_vintage": null,
        "state": "never_fetched"
      },
      "nm_ocd_wcproduction": {
        "declared_vintage": null,
        "retrieval_vintage": null,
        "state": "never_fetched"
      },
      "nm_ocd_wellhistory": {
        "declared_vintage": null,
        "retrieval_vintage": null,
        "state": "never_fetched"
      },
      "proj_grid_nad27": {
        "declared_vintage": null,
        "retrieval_vintage": null,
        "state": "never_fetched"
      },
      "tx_gis_wells_county": {
        "declared_vintage": null,
        "retrieval_vintage": null,
        "state": "never_fetched"
      },
      "tx_wellbore_ewa_csv": {
        "declared_vintage": null,
        "retrieval_vintage": null,
        "state": "never_fetched"
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
    "glossary": "/v1/glossary",
    "glossary_index": "/v1/glossary/index",
    "health": "/v1/health",
    "manifests": "/v1/manifests",
    "next": null,
    "openapi": "/openapi.json",
    "quarantine": "/v1/quarantine",
    "self": "/v1",
    "tiles": "/v1/tiles",
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
    "request_id": "01M0HWF80N2R1EGSYQHJTQWGN5",
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
        "count": 2,
        "key": "unknown_vocab",
        "share": 0.666667
      },
      {
        "count": 1,
        "key": "impossible_volume",
        "share": 0.333333
      }
    ],
    "total": 3
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
    "request_id": "01M0HWF80Z6S7SS83R7MHVS5GE",
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
      "/granularity": "gt_granularity"
    },
    "next_cursor": null,
    "request_id": "01M0HWF8188A2RBE8MS9PV4VY8",
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
    "request_id": "01M0HWF81M28DDXG22M1RXRZAY",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/quarantine?limit=2` — list_quarantine. */
export const pagedQuarantineEnvelope = {
  "data": [
    {
      "first_seen_at": "2026-08-01T05:02:11+00:00",
      "first_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "last_seen_at": "2026-08-01T05:02:11+00:00",
      "last_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "notes": null,
      "occurrence_count": 2,
      "quarantine_id": "qr_01contract0003",
      "reason_code": "unknown_vocab",
      "release_derivation_id": null,
      "released_at": null,
      "released_by_rule_id": null,
      "row_fingerprint": "fp_contract_0003",
      "rule_id": "cr_nd_status_vocab_1",
      "source_id": "nd_gis_wells",
      "stage": "conform",
      "staging_table": "staging.nd_gis_wells",
      "state": "released"
    },
    {
      "first_seen_at": "2026-08-01T05:02:11+00:00",
      "first_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "last_seen_at": "2026-08-01T05:02:11+00:00",
      "last_seen_manifest_id": "man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
      "notes": null,
      "occurrence_count": 1,
      "quarantine_id": "qr_01contract0002",
      "reason_code": "impossible_volume",
      "release_derivation_id": null,
      "released_at": null,
      "released_by_rule_id": null,
      "row_fingerprint": "fp_contract_0002",
      "rule_id": "cr_nd_volume_range_1",
      "source_id": "nd_mpr_xlsx",
      "stage": "validate",
      "staging_table": "staging.nd_mpr_oil",
      "state": "open"
    }
  ],
  "links": {
    "explain": null,
    "next": "/v1/quarantine?limit=2&cursor=eyJrIjoiMjAyNi0wOC0wMVQwNTowMjoxMSswMDowMCIsInEiOiI0NDEzNmZhMyIsInQiOiJxcl8wMWNvbnRyYWN0MDAwMiIsInYiOm51bGx9",
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
      "/state": "gt_quarantine"
    },
    "next_cursor": "eyJrIjoiMjAyNi0wOC0wMVQwNTowMjoxMSswMDowMCIsInEiOiI0NDEzNmZhMyIsInQiOiJxcl8wMWNvbnRyYWN0MDAwMiIsInYiOm51bGx9",
    "request_id": "01M0HWF822ENYS3H9TJ9WFTP6K",
    "source_freshness": {},
    "warnings": []
  }
};
