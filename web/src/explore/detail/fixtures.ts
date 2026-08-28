// Recorded from the tracked `tests/support/serve_branch.py` harness by
// `scripts/record-explorer-fixtures.py`. Request ids are normalized because they are volatile
// D3 envelope metadata; every other value is the locally served branch response.
//
// Collection and detail fixtures come from the same seeded database, so each detail id names
// the exact row carried by the collection fixture. The owner key is never written.

/** `GET /v1/quarantine/qr_01explorer0059` — get_quarantine_row. */
export const quarantineDetailEnvelope = {
  "data": {
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
    "row_payload": {
      "row": 59,
      "stream_raw": "GasSold"
    },
    "rule_id": "cr_nd_stream_vocab_1",
    "source_id": "nd_gis_wells",
    "stage": "parse",
    "staging_table": "staging.nd_mpr_oil",
    "state": "accepted_loss"
  },
  "links": {
    "explain": null,
    "next": null,
    "self": "/v1/quarantine/qr_01explorer0059"
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
    "next_cursor": null,
    "request_id": "00000000000000000000000000",
    "source_freshness": {},
    "warnings": []
  }
};

/** `GET /v1/conformance/cr_nd_stream_vocab_1` — get_conformance_rule. */
export const conformanceRuleEnvelope = {
  "data": {
    "applies_to_fields": [
      "stream_raw"
    ],
    "code_ref": null,
    "effective_from": "2026-01-01",
    "effective_to": null,
    "evidence_sha256": null,
    "evidence_url": "https://www.dmr.nd.gov/oilgas/mpr/2026_03.xlsx",
    "published_vintage": "2026-08-20",
    "rationale": "canonical.production_monthly admits oil, gas and water only. GasSold and Flared are dispositions of produced gas, not streams: they are recorded in nd_stream_map as not promoted and quarantine with a reason, so conflict C7's claim is measured rather than asserted. The rule reads the promoted view because the executor stringifies lookup values and a NULL would promote as the text 'None'.",
    "rule": "Promote Oil, Wtr and Gas; quarantine every other reported column as a disposition.",
    "rule_family": "cr_nd_stream_vocab",
    "rule_id": "cr_nd_stream_vocab_1",
    "rule_kind": "vocab_map",
    "source_id": "nd_mpr_xlsx",
    "spec": {
      "key_col": "stream_raw",
      "mapping_table": "nd_stream_promoted_map",
      "reason_code": "stream_not_promoted",
      "unmapped_action": "quarantine",
      "value_col": "stream_canonical"
    },
    "stage": "conform",
    "supersedes_rule_id": null
  },
  "links": {
    "explain": null,
    "next": null,
    "self": "/v1/conformance/cr_nd_stream_vocab_1"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": "2026-08-28"
    },
    "deprecations": [],
    "labels": {
      "/rule_id": "gt_conformance_rule",
      "/spec": "gt_conformance_rule"
    },
    "next_cursor": null,
    "request_id": "00000000000000000000000000",
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
    "request_id": "00000000000000000000000000",
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
    "request_id": "00000000000000000000000000",
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
    "request_id": "00000000000000000000000000",
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
    "geometry_provenance": [
      "lateral"
    ],
    "land_unit_label": "151N-101W-11",
    "lateral_count": 1,
    "lateral_length_ft": {
      "d": "drv_vqkc2aza4pwtxpeonuxa#api10=3305310451&col=lateral_length_ft",
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
    "completions": "/v1/wells/3305310451/completions",
    "explain": "/v1/explain?h=drv_vqkc2aza4pwtxpeonuxa%23api10%3D3305310451%26col%3Dlateral_length_ft&depth=full",
    "formations": "/v1/formations",
    "neighbors": "/v1/wells/3305310451/neighbors",
    "next": null,
    "production": "/v1/wells/3305310451/production",
    "self": "/v1/wells/3305310451"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": "2026-08-20"
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
    "request_id": "00000000000000000000000000",
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
    "effective_from": "2026-08-28",
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
    "request_id": "00000000000000000000000000",
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
    "request_id": "00000000000000000000000000",
    "source_freshness": {},
    "warnings": []
  }
};
