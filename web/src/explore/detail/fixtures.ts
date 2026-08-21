// Recorded from a locally-served build of this branch on 2026-08-21, one per operation the
// eleven datasets name as their `detail_operation`. `work-output/explorer-c8-serve.py` stands
// the stack up and `work-output/explorer-c8-record.py` writes this file — it is refreshed, not
// edited, for the reason `web/src/test/fixtures.ts:1-10` gives.
//
//   curl -H "X-Glasswell-Key: $KEY" .../v1/quarantine/qr_01contract0003
//   curl -H "X-Glasswell-Key: $KEY" .../v1/conformance/cr_nd_status_vocab_1
//   …one per exported constant below, each named for the operation it came from.
//
// The ids are the ones C7's collection fixtures already carry, so a row and its record are
// the same row rather than two plausible ones.
//
// A detail response is the reason §3.4 exists: `get_quarantine_row` carries `row_payload` and
// the first/last-seen manifests, which the collection does not, and `get_vintage` carries the
// `_lineage` sidecar its list form omits. The owner key travels in the header and appears in
// no body here — the recorder asserts that before writing.

/** `GET /v1/quarantine/qr_01contract0003` — get_quarantine_row. */
export const quarantineDetailEnvelope = {
  "data": {
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
    "row_payload": {
      "status": "MYSTERY"
    },
    "rule_id": "cr_nd_status_vocab_1",
    "source_id": "nd_gis_wells",
    "stage": "conform",
    "staging_table": "staging.nd_gis_wells",
    "state": "released"
  },
  "links": {
    "explain": null,
    "next": null,
    "self": "/v1/quarantine/qr_01contract0003"
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
    "request_id": "01M0J67HNMJ05EF0A3BS6X0GST",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/conformance/cr_nd_status_vocab_1` — get_conformance_rule. */
export const conformanceRuleEnvelope = {
  "data": {
    "applies_to_fields": [
      "status"
    ],
    "code_ref": null,
    "effective_from": "2026-01-01",
    "effective_to": null,
    "evidence_sha256": null,
    "evidence_url": "https://gis.dmr.nd.gov/downloads/oilgas/shapefile/OGD_Wells.zip",
    "rationale": "Measured from OGD_Wells.dbf (43,812 records): A 20640, PA 6447, DRY 6347, PNC 5725, IA 1597, Confidential 962, AB 842, LOC 610, DRL 340, TA 174, TAO 30, PANF 27, EXP 22, PNS 20, TASC 11, TATD 8, NC 7, LOCR 2, NJ 1. The canonical set is active, plugged, dry, permitted, inactive, confidential, drilling, temporarily_abandoned and expired; the permit-lifecycle terminal codes collapse to expired. Confidential is a status, which is why the well record carries a confidential flag and why withheld is a distinct state from missing (\u00a73.0.3).",
    "rule": "Map the NDIC well-status code to the canonical status vocabulary.",
    "rule_family": "cr_nd_status_vocab",
    "rule_id": "cr_nd_status_vocab_1",
    "rule_kind": "vocab_map",
    "source_id": "nd_gis_wells",
    "spec": {
      "key_col": "status",
      "mapping_table": "nd_status_map",
      "reason_code": "unknown_status",
      "unmapped_action": "quarantine",
      "value_col": "status_canonical"
    },
    "stage": "conform",
    "supersedes_rule_id": null
  },
  "links": {
    "explain": null,
    "next": null,
    "self": "/v1/conformance/cr_nd_status_vocab_1"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {
      "/rule_id": "gt_conformance_rule",
      "/spec": "gt_conformance_rule"
    },
    "next_cursor": null,
    "request_id": "01M0J67HP32CA1VF0EHGCCDZGE",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/manifests/man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee` — get_manifest. */
export const manifestEnvelope = {
  "data": {
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
  "links": {
    "explain": null,
    "next": null,
    "self": "/v1/manifests/man_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    "source": "/v1/manifests?source_id=nd_mpr_xlsx"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": "2026-08-01"
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": null,
    "request_id": "01M0J67HPGGWC2TDWGB7J11W7Y",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/vintages/vin_nd_gis_wells_2026-08-01` — get_vintage. */
export const vintageEnvelope = {
  "data": {
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
  "links": {
    "explain": "/v1/explain?h=drv_obqajdni25f25zmxcz7a&depth=full",
    "next": null,
    "self": "/v1/vintages/vin_nd_gis_wells_2026-08-01",
    "source": "/v1/vintages?source_id=nd_gis_wells"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": "2026-08-01"
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": null,
    "request_id": "01M0J67HPX67VV24PZ0GAT7G3P",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/derivations/drv_obqajdni25f25zmxcz7a` — get_derivation. */
export const derivationEnvelope = {
  "data": {
    "code_dirty": false,
    "code_version": "git:0000test",
    "correlation_id": "run_contract",
    "created_at": "2026-08-01T05:00:00+00:00",
    "created_vintage": "2026-08-01",
    "derivation_id": "drv_obqajdni25f25zmxcz7a",
    "determinism_class": "D1",
    "duration_ms": 0,
    "env_id": "env_test",
    "model_id": null,
    "operation": "canonical.promote",
    "output": {
      "dataset": "canonical.production_monthly",
      "locator": "",
      "partition": {
        "report_vintage": "2026-08-01",
        "source_id": "nd_mpr_xlsx"
      },
      "rows": 18,
      "sha256": "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1",
      "store": "postgres"
    },
    "params": {
      "source_id": "nd_mpr_xlsx"
    },
    "params_hash": "17de6c04ce2a321b09810a3d6c3c4296d110250449250767a5ced0ab65bf55cd",
    "recipe_id": null,
    "status": "ok"
  },
  "links": {
    "explain": "/v1/explain?h=drv_obqajdni25f25zmxcz7a&depth=full",
    "next": null,
    "self": "/v1/derivations/drv_obqajdni25f25zmxcz7a"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": "2026-08-01"
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": null,
    "request_id": "01M0J67HQ7NJ5H4B1RHFBX42ZP",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/wells/3305310451` — get_well. */
export const wellDetailEnvelope = {
  "data": {
    "api10": "3305310451",
    "api14": "33053104510000",
    "basin": "williston",
    "completion_date": null,
    "compute_crs": "EPSG:4326",
    "confidential_flag": false,
    "county_code_at_permit": "053",
    "effective_from": "2026-08-01",
    "geometry": [
      {
        "geom_key": "33053104510000_LAT1",
        "geom_type": "lateral",
        "source_datum": "EPSG:4269"
      }
    ],
    "land_unit_label": "151N-101W-11",
    "lateral_count": 1,
    "lateral_length_ft": {
      "d": "drv_tcfhfxnptv2oucdmjtzq#api10=3305310451&col=lateral_length_ft",
      "unit": "ft",
      "value": "9862.27"
    },
    "length_method": "geodesic",
    "links": {
      "production": "/v1/wells/3305310451/production",
      "self": "/v1/wells/3305310451"
    },
    "ndic_file_no": "22023",
    "operator_name_reported": "DEVON ENERGY WILLISTON, L.L.C",
    "spud_date": "2019-05-27",
    "state_code": "33",
    "status_canonical": "active",
    "status_reported": "A",
    "storage_crs": "EPSG:4326",
    "surface_point": null,
    "total_depth_ft": null,
    "well_name": "BILL 14-23 1H",
    "well_type_reported": "OG"
  },
  "links": {
    "explain": "/v1/explain?h=drv_tcfhfxnptv2oucdmjtzq%23api10%3D3305310451%26col%3Dlateral_length_ft&depth=full",
    "next": null,
    "production": "/v1/wells/3305310451/production",
    "self": "/v1/wells/3305310451"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": "2026-08-01"
    },
    "deprecations": [],
    "labels": {
      "/api10": "gt_api_10_api_12_api_14",
      "/confidential_flag": "gt_confidential_well",
      "/land_unit_label": "gt_land_unit",
      "/lateral_length_ft": "gt_wellbore",
      "/total_depth_ft": "gt_wellbore"
    },
    "next_cursor": null,
    "request_id": "01M0J67HQH5VR8YCABVKW0M2HE",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/glossary/gt_analog` — get_glossary_term. */
export const glossaryTermEnvelope = {
  "data": {
    "aliases": [],
    "appears_in": [],
    "domain_tags": [
      "modeling"
    ],
    "effective_from": "2026-08-21",
    "expanded_definition": "A neighbour is near in metres; an analog is near in the variables that drive performance. Confusing the two is how a comparison set ends up full of wells that share a section and nothing else.",
    "first_surfaced_in": null,
    "highlightable": false,
    "related_terms": [
      "Type curve",
      "Training support"
    ],
    "short_definition": "A well near another in feature space - rock, design, location - rather than in physical space.",
    "source_refs": [
      "blueprint-v0.6 \u00a79"
    ],
    "term": "Analog",
    "term_id": "gt_analog"
  },
  "links": {
    "explain": null,
    "next": null,
    "self": "/v1/glossary/gt_analog"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": null,
    "request_id": "01M0J67HRGRN08HQG19T1W3VQ4",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/errors/cursor_query_mismatch` — get_error_type. */
export const errorTypeEnvelope = {
  "data": {
    "code": "cursor_query_mismatch",
    "description": "The cursor was minted against a different filter set. Continuing would return a page from a different result set (SB-04 \u00a72.3).",
    "emitted_by_this_slice": true,
    "status": 422,
    "title": "Cursor does not match this query",
    "type": "/v1/errors/cursor_query_mismatch"
  },
  "links": {
    "explain": null,
    "next": null,
    "self": "/v1/errors/cursor_query_mismatch"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": null,
    "request_id": "01M0J67HRVEPQ844FJRMF941JC",
    "source_freshness": {},
    "warnings": []
  }
};
