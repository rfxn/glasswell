// Recorded from the deployed instance on 2026-08-20, not hand-written from the router
// source, so a shape drift in the API fails a web test rather than the owner's first click:
//   curl -K <keyfile> https://glasswell.lab.rpx.sh/v1/wells/3305310451
//   curl -K <keyfile> .../v1/wells/3305310451/production
//   curl -K <keyfile> -G .../v1/explain --data-urlencode "h=<oil handle>" --data-urlencode depth=full
//   curl -K <keyfile> .../v1/glossary/index   and   .../v1/glossary?limit=200
// The owner key travels in the X-Glasswell-Key header and appears in no response body.
// The glossary payloads are the recorded envelopes filtered to the terms these tests use.
// The oil column spans six monthly promotions, so `_lineage` keys a handle per point
// (`series.oil_bbl.0`) and OIL_HANDLE is the first of them (SB-07 §9.3).

export const API10 = "3305310451";
export const LENGTH_HANDLE = "drv_ga3f2mao5zgyb5xcniwq#api10=3305310451&col=lateral_length_ft";
export const OIL_HANDLE = "drv_xwfwmpqifwfcsspnyjqq#api10=3305310451&col=oil_bbl&pm=2025-10";
export const SHA256 = "a5cbbe40fe0e49b116e279079996c4ecfda6757450c6f43b14fff66bc160b7b5";

export const wellEnvelope = {
  "data": {
    "api10": "3305310451",
    "api14": "33053104510000",
    "basin": null,
    "compute_crs": "EPSG:4326",
    "confidential_flag": false,
    "county_code_at_permit": "053",
    "effective_from": "2026-08-20",
    "geometry": [
      {
        "geom_key": "33053104510000_LAT1",
        "geom_type": "lateral",
        "source_datum": "EPSG:4269"
      },
      {
        "geom_key": "surface",
        "geom_type": "surface",
        "source_datum": "EPSG:4269"
      }
    ],
    "land_unit_label": "149N-94W-20",
    "lateral_count": 1,
    "lateral_length_ft": {
      "d": "drv_ga3f2mao5zgyb5xcniwq#api10=3305310451&col=lateral_length_ft",
      "unit": "ft",
      "value": "15065.44"
    },
    "length_method": "geodesic",
    "links": {
      "production": "/v1/wells/3305310451/production",
      "self": "/v1/wells/3305310451"
    },
    "ndic_file_no": "41425",
    "operator_name_reported": "EOG RESOURCES, INC.",
    "spud_date": "2025-01-05",
    "state_code": "33",
    "status_canonical": "active",
    "status_reported": "A",
    "storage_crs": "EPSG:4326",
    "surface_point": {
      "lat": 47.71073912,
      "lon": -102.7482137
    },
    "well_name": "Mandaree 50-2008H",
    "well_type_reported": "OG"
  },
  "links": {
    "completions": "/v1/wells/3305310451/completions",
    "explain": "/v1/explain?h=drv_ga3f2mao5zgyb5xcniwq%23api10%3D3305310451%26col%3Dlateral_length_ft&depth=full",
    "formations": "/v1/formations",
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
      "/lateral_length_ft": "gt_wellbore"
    },
    "next_cursor": null,
    "request_id": "01M0FWZNVS88J142QCKY0XT2C0",
    "source_freshness": {},
    "warnings": [
      {
        "code": "geometry_not_promoted",
        "detail": "1 horizontal geometry rows for this well (VERT) were not promoted: segment_not_promoted under cr_nd_segment_vocab_1. They are in /v1/quarantine with their payloads.",
        "pointer": "/geometry"
      }
    ]
  }
};

// Constructed for the additive completions contract before its first deployment. These values
// exercise source-honest rendering and make no claim about the recorded well above.
export const completionContextEnvelope = {
  "data": {
    "api10": "3305310451",
    "design_availability": "not_promoted",
    "events": [
      {
        "event_id": "ff-3305310451-20250424",
        "event_kind": "hydraulic_frac_job_end",
        "job_start_date": "2025-04-11",
        "completion_date": "2025-04-24",
        "source_id": "fracfocus_csv",
        "report_vintage": "2026-08-20",
        "_lineage": {
          "job_start_date": "drv_context_event#disclosure_id=ff-3305310451-20250424&col=job_start_date",
          "completion_date": "drv_context_event#disclosure_id=ff-3305310451-20250424&col=completion_date"
        }
      }
    ],
    "pools": [
      {
        "completion_key": "3305310451:BAKKEN",
        "well_completion_pool": "3305310451:BAKKEN",
        "pool_reported": "BAKKEN",
        "formation": "bakken",
        "formation_group": "bakken",
        "formation_null_semantics": "mapped",
        "source_id": "nd_mpr_xlsx",
        "first_production_month": "2025-10-01",
        "last_production_month": "2026-03-01",
        "effective_from": null,
        "latest_report_vintage": "2026-08-20",
        "_lineage": {
          "pool_reported": "drv_context_pool#completion_key=3305310451:BAKKEN&col=pool_reported&pm=2026-03",
          "first_production_month": "drv_context_pool#completion_key=3305310451:BAKKEN&col=production_month&pm=2025-10",
          "last_production_month": "drv_context_pool#completion_key=3305310451:BAKKEN&col=production_month&pm=2026-03",
          "latest_report_vintage": "drv_context_pool#completion_key=3305310451:BAKKEN&col=report_vintage&pm=2026-03"
        }
      }
    ]
  },
  "links": {
    "next": null,
    "self": "/v1/wells/3305310451/completions",
    "well": "/v1/wells/3305310451"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": "2026-08-20"
    },
    "deprecations": [],
    "labels": {
      "/api10": "gt_api_10_api_12_api_14",
      "/events/0/event_kind": "gt_completion_event",
      "/events/0/completion_date": "gt_completion_event",
      "/events/0/source_id": "gt_source",
      "/events/0/report_vintage": "gt_report_vintage",
      "/pools/0/well_completion_pool": "gt_pool",
      "/pools/0/pool_reported": "gt_pool",
      "/pools/0/formation": "gt_formation",
      "/pools/0/formation_group": "gt_formation",
      "/pools/0/source_id": "gt_source",
      "/pools/0/first_production_month": "gt_production_month",
      "/pools/0/last_production_month": "gt_production_month",
      "/pools/0/latest_report_vintage": "gt_report_vintage"
    },
    "next_cursor": null,
    "request_id": "01M0J8C5AFQ9CJRPXCVX3A8A78",
    "source_freshness": {
      "fracfocus_csv": {
        "declared_vintage": "2026-08-20",
        "retrieval_vintage": "2026-08-20",
        "state": "current"
      },
      "nd_mpr_xlsx": {
        "declared_vintage": "2026-08-20",
        "retrieval_vintage": "2026-08-20",
        "state": "current"
      }
    },
    "warnings": []
  }
};

export const productionEnvelope = {
  "data": {
    "_basis": {
      "series.oil_bbl": "oil+condensate",
      "series.water_bbl": "water"
    },
    "_lineage": {
      "series.gas_mcf.0": "drv_xwfwmpqifwfcsspnyjqq#api10=3305310451&col=gas_mcf&pm=2025-10",
      "series.gas_mcf.1": "drv_dgnvicc2znev6vip7u4q#api10=3305310451&col=gas_mcf&pm=2025-11",
      "series.gas_mcf.2": "drv_f4qsx42ni5srjjefyvfa#api10=3305310451&col=gas_mcf&pm=2025-12",
      "series.gas_mcf.3": "drv_k2jviajgphaxa6mbu6fq#api10=3305310451&col=gas_mcf&pm=2026-01",
      "series.gas_mcf.4": "drv_rwmstnuow7qs2r67l37a#api10=3305310451&col=gas_mcf&pm=2026-02",
      "series.gas_mcf.5": "drv_6xj33kv4kjbzpbjeh76q#api10=3305310451&col=gas_mcf&pm=2026-03",
      "series.oil_bbl.0": "drv_xwfwmpqifwfcsspnyjqq#api10=3305310451&col=oil_bbl&pm=2025-10",
      "series.oil_bbl.1": "drv_dgnvicc2znev6vip7u4q#api10=3305310451&col=oil_bbl&pm=2025-11",
      "series.oil_bbl.2": "drv_f4qsx42ni5srjjefyvfa#api10=3305310451&col=oil_bbl&pm=2025-12",
      "series.oil_bbl.3": "drv_k2jviajgphaxa6mbu6fq#api10=3305310451&col=oil_bbl&pm=2026-01",
      "series.oil_bbl.4": "drv_rwmstnuow7qs2r67l37a#api10=3305310451&col=oil_bbl&pm=2026-02",
      "series.oil_bbl.5": "drv_6xj33kv4kjbzpbjeh76q#api10=3305310451&col=oil_bbl&pm=2026-03",
      "series.water_bbl.0": "drv_xwfwmpqifwfcsspnyjqq#api10=3305310451&col=water_bbl&pm=2025-10",
      "series.water_bbl.1": "drv_dgnvicc2znev6vip7u4q#api10=3305310451&col=water_bbl&pm=2025-11",
      "series.water_bbl.2": "drv_f4qsx42ni5srjjefyvfa#api10=3305310451&col=water_bbl&pm=2025-12",
      "series.water_bbl.3": "drv_k2jviajgphaxa6mbu6fq#api10=3305310451&col=water_bbl&pm=2026-01",
      "series.water_bbl.4": "drv_rwmstnuow7qs2r67l37a#api10=3305310451&col=water_bbl&pm=2026-02",
      "series.water_bbl.5": "drv_6xj33kv4kjbzpbjeh76q#api10=3305310451&col=water_bbl&pm=2026-03"
    },
    "_units": {
      "series.gas_mcf": "mcf",
      "series.oil_bbl": "bbl",
      "series.water_bbl": "bbl"
    },
    "api10": "3305310451",
    "granularity": "well_observed",
    "series": {
      "gas_mcf": [
        "76126.000",
        "85063.000",
        "49578.000",
        "69677.000",
        "61647.000",
        "56896.000"
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
        "2026-08-20",
        "2026-08-20",
        "2026-08-20",
        "2026-08-20",
        "2026-08-20",
        "2026-08-20"
      ],
      "oil_bbl": [
        "70965.000",
        "73959.000",
        "43531.000",
        "57199.000",
        "49328.000",
        "43237.000"
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
        "2026-08-20",
        "2026-08-20",
        "2026-08-20",
        "2026-08-20",
        "2026-08-20",
        "2026-08-20"
      ],
      "pm": [
        "2025-10",
        "2025-11",
        "2025-12",
        "2026-01",
        "2026-02",
        "2026-03"
      ],
      "water_bbl": [
        "47601.000",
        "45428.000",
        "24918.000",
        "30985.000",
        "24753.000",
        "22452.000"
      ],
      "water_bbl_null_semantics": [
        "reported",
        "reported",
        "reported",
        "reported",
        "reported",
        "reported"
      ],
      "water_bbl_report_vintage": [
        "2026-08-20",
        "2026-08-20",
        "2026-08-20",
        "2026-08-20",
        "2026-08-20",
        "2026-08-20"
      ]
    },
    "source_id": "nd_mpr_xlsx",
    "streams": [
      "oil",
      "gas",
      "water"
    ]
  },
  "links": {
    "explain": "/v1/explain?h=drv_xwfwmpqifwfcsspnyjqq%23api10%3D3305310451%26col%3Doil_bbl%26pm%3D2025-10&h=drv_dgnvicc2znev6vip7u4q%23api10%3D3305310451%26col%3Doil_bbl%26pm%3D2025-11&h=drv_f4qsx42ni5srjjefyvfa%23api10%3D3305310451%26col%3Doil_bbl%26pm%3D2025-12&h=drv_k2jviajgphaxa6mbu6fq%23api10%3D3305310451%26col%3Doil_bbl%26pm%3D2026-01&h=drv_rwmstnuow7qs2r67l37a%23api10%3D3305310451%26col%3Doil_bbl%26pm%3D2026-02&h=drv_6xj33kv4kjbzpbjeh76q%23api10%3D3305310451%26col%3Doil_bbl%26pm%3D2026-03&h=drv_xwfwmpqifwfcsspnyjqq%23api10%3D3305310451%26col%3Dgas_mcf%26pm%3D2025-10&h=drv_dgnvicc2znev6vip7u4q%23api10%3D3305310451%26col%3Dgas_mcf%26pm%3D2025-11&h=drv_f4qsx42ni5srjjefyvfa%23api10%3D3305310451%26col%3Dgas_mcf%26pm%3D2025-12&h=drv_k2jviajgphaxa6mbu6fq%23api10%3D3305310451%26col%3Dgas_mcf%26pm%3D2026-01&h=drv_rwmstnuow7qs2r67l37a%23api10%3D3305310451%26col%3Dgas_mcf%26pm%3D2026-02&h=drv_6xj33kv4kjbzpbjeh76q%23api10%3D3305310451%26col%3Dgas_mcf%26pm%3D2026-03&h=drv_xwfwmpqifwfcsspnyjqq%23api10%3D3305310451%26col%3Dwater_bbl%26pm%3D2025-10&h=drv_dgnvicc2znev6vip7u4q%23api10%3D3305310451%26col%3Dwater_bbl%26pm%3D2025-11&h=drv_f4qsx42ni5srjjefyvfa%23api10%3D3305310451%26col%3Dwater_bbl%26pm%3D2025-12&h=drv_k2jviajgphaxa6mbu6fq%23api10%3D3305310451%26col%3Dwater_bbl%26pm%3D2026-01&h=drv_rwmstnuow7qs2r67l37a%23api10%3D3305310451%26col%3Dwater_bbl%26pm%3D2026-02&h=drv_6xj33kv4kjbzpbjeh76q%23api10%3D3305310451%26col%3Dwater_bbl%26pm%3D2026-03&depth=full",
    "next": null,
    "self": "/v1/wells/3305310451/production",
    "well": "/v1/wells/3305310451"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": "2026-08-20"
    },
    "deprecations": [],
    "labels": {
      "/api10": "gt_api_10_api_12_api_14",
      "/granularity": "gt_granularity",
      "/series/gas_mcf": "gt_stream",
      "/series/gas_mcf_null_semantics": "gt_withheld",
      "/series/gas_mcf_report_vintage": "gt_report_vintage",
      "/series/oil_bbl": "gt_liquids_policy",
      "/series/oil_bbl_null_semantics": "gt_withheld",
      "/series/oil_bbl_report_vintage": "gt_report_vintage",
      "/series/water_bbl": "gt_stream",
      "/series/water_bbl_null_semantics": "gt_withheld",
      "/series/water_bbl_report_vintage": "gt_report_vintage"
    },
    "next_cursor": null,
    "request_id": "01M0FWZP769264Z7EQ2SFP734D",
    "source_freshness": {
      "nd_mpr_xlsx": {
        "declared_vintage": "2026-08-20",
        "retrieval_vintage": "2026-08-20",
        "state": "current"
      }
    },
    "warnings": [
      {
        "code": "series_spans_derivations",
        "detail": "6 derivations contributed to this column; _lineage carries one handle per point",
        "pointer": "/series/oil_bbl"
      },
      {
        "code": "series_spans_derivations",
        "detail": "6 derivations contributed to this column; _lineage carries one handle per point",
        "pointer": "/series/gas_mcf"
      },
      {
        "code": "series_spans_derivations",
        "detail": "6 derivations contributed to this column; _lineage carries one handle per point",
        "pointer": "/series/water_bbl"
      }
    ]
  }
};

export const explainEnvelope = {
  "data": {
    "chains": [
      {
        "as_of_vintage": "2026-08-20",
        "depth": 2,
        "edges": [
          {
            "as_of_vintage": "2026-08-20",
            "from": "drv_xwfwmpqifwfcsspnyjqq",
            "role": "primary",
            "to": "man_a5cbbe40fe0e49b116e279079996c4ec"
          },
          {
            "as_of_vintage": "2026-08-20",
            "from": "drv_xwfwmpqifwfcsspnyjqq",
            "role": "primary",
            "to": "drv_nz6rba6dbanbhilyzluq"
          },
          {
            "as_of_vintage": "2026-08-20",
            "from": "drv_nz6rba6dbanbhilyzluq",
            "role": "primary",
            "to": "man_a5cbbe40fe0e49b116e279079996c4ec"
          }
        ],
        "handle": "drv_xwfwmpqifwfcsspnyjqq#api10=3305310451&col=oil_bbl&pm=2025-10",
        "nodes": [
          {
            "code_version": "pkg:0.1.0",
            "conformance_rules": [
              {
                "family": "cr_nd_days_range",
                "kind": "validity_filter",
                "rule_id": "cr_nd_days_range_1"
              },
              {
                "family": "cr_nd_stream_vocab",
                "kind": "vocab_map",
                "rule_id": "cr_nd_stream_vocab_1"
              },
              {
                "family": "cr_nd_units",
                "kind": "unit_conform",
                "rule_id": "cr_nd_units_1"
              },
              {
                "family": "cr_nd_volume_range",
                "kind": "validity_filter",
                "rule_id": "cr_nd_volume_range_1"
              }
            ],
            "created_vintage": "2026-08-20",
            "determinism_class": "D1",
            "explanation": "canonical.promote produced canonical.production_monthly (manifest_id=man_a5cbbe40fe0e49b116e279079996c4ec, month=2025-10), 65376 rows, at code pkg:0.1.0; conformance rules cr_nd_days_range_1, cr_nd_stream_vocab_1, cr_nd_units_1, cr_nd_volume_range_1.",
            "id": "drv_xwfwmpqifwfcsspnyjqq",
            "model_id": null,
            "operation": "canonical.promote",
            "output": {
              "dataset": "canonical.production_monthly",
              "partition": {
                "manifest_id": "man_a5cbbe40fe0e49b116e279079996c4ec",
                "month": "2025-10"
              },
              "rows": 65376,
              "sha256": "916016a2bb2e335b2ea0a9c6ccb796fb17c0a0d8eb4177d2b24cd87c907e8b76",
              "store": "postgres"
            },
            "params_hash": "4b81d19fed42aa1ef76b40640b4d59754a0dbf0a533c8dd2e378ba903f7c0e4f",
            "recipe_id": null,
            "status": "ok",
            "type": "derivation"
          },
          {
            "acquisition_method": "https_get",
            "acquisition_url": "https://www.dmr.nd.gov/oilgas/mpr/2025_10.xlsx",
            "bytes": 3247051,
            "explanation": "nd_mpr_xlsx 2025_10.xlsx, fetched 2026-08-20T08:07:51.387152+00:00 via https_get; sha256 a5cbbe40fe0e.",
            "fetch_vintage": "2026-08-20",
            "fetched_at": "2026-08-20T08:07:51.387152+00:00",
            "id": "man_a5cbbe40fe0e49b116e279079996c4ec",
            "redistributable": false,
            "sha256": "a5cbbe40fe0e49b116e279079996c4ecfda6757450c6f43b14fff66bc160b7b5",
            "source_id": "nd_mpr_xlsx",
            "source_key": "2025_10.xlsx",
            "supersedes": null,
            "type": "manifest"
          },
          {
            "code_version": "pkg:0.1.0",
            "conformance_rules": [
              {
                "family": "cr_nd_api_identity",
                "kind": "parse_directive",
                "rule_id": "cr_nd_api_identity_1"
              },
              {
                "family": "cr_nd_land_unit",
                "kind": "parse_directive",
                "rule_id": "cr_nd_land_unit_1"
              },
              {
                "family": "cr_nd_month_convention",
                "kind": "parse_directive",
                "rule_id": "cr_nd_month_convention_1"
              },
              {
                "family": "cr_nd_mpr_format",
                "kind": "parse_directive",
                "rule_id": "cr_nd_mpr_format_1"
              }
            ],
            "created_vintage": "2026-08-20",
            "determinism_class": "D1",
            "explanation": "stage.parse produced staging.nd_mpr_oil (manifest_id=man_a5cbbe40fe0e49b116e279079996c4ec, month=2025-10), 22056 rows, at code pkg:0.1.0; conformance rules cr_nd_api_identity_1, cr_nd_land_unit_1, cr_nd_month_convention_1, cr_nd_mpr_format_1.",
            "id": "drv_nz6rba6dbanbhilyzluq",
            "model_id": null,
            "operation": "stage.parse",
            "output": {
              "dataset": "staging.nd_mpr_oil",
              "partition": {
                "manifest_id": "man_a5cbbe40fe0e49b116e279079996c4ec",
                "month": "2025-10"
              },
              "rows": 22056,
              "sha256": "f27f5be836ac598388aa333b9191082ba15af24699029f1d1584948937ca206a",
              "store": "postgres"
            },
            "params_hash": "d1e6f03cd786a97a7b586bb2ae65fad78afda7975a339353030cc5f79fce8b4e",
            "recipe_id": null,
            "status": "ok",
            "type": "derivation"
          }
        ],
        "recipe": null,
        "root": "drv_xwfwmpqifwfcsspnyjqq",
        "terminals": [
          "man_a5cbbe40fe0e49b116e279079996c4ec"
        ],
        "truncated": false,
        "warnings": []
      }
    ]
  },
  "links": {
    "explain": null,
    "next": null,
    "self": "/v1/explain"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": null,
    "request_id": "01M0FWZPH9ACVH23HKPC6KQ05Q",
    "source_freshness": {},
    "warnings": []
  }
};

export const glossaryIndexEnvelope = {
  "data": {
    "entries": [
      {
        "n_words": 5,
        "surface": "api-10 / api-12 / api-14",
        "term_id": "gt_api_10_api_12_api_14"
      },
      {
        "n_words": 2,
        "surface": "api number",
        "term_id": "gt_api_10_api_12_api_14"
      },
      {
        "n_words": 2,
        "surface": "liquids policy",
        "term_id": "gt_liquids_policy"
      },
      {
        "n_words": 1,
        "surface": "api-10",
        "term_id": "gt_api_10_api_12_api_14"
      },
      {
        "n_words": 1,
        "surface": "api-12",
        "term_id": "gt_api_10_api_12_api_14"
      },
      {
        "n_words": 1,
        "surface": "api-14",
        "term_id": "gt_api_10_api_12_api_14"
      },
      {
        "n_words": 1,
        "surface": "granularity",
        "term_id": "gt_granularity"
      }
    ],
    "index_version": "gix_12af68c21f89",
    "stopwords": [
      "analog",
      "band",
      "slot",
      "spine",
      "stream",
      "vintage",
      "vintage (well vintage)",
      "water cut",
      "well vintage",
      "wellbore",
      "withheld"
    ]
  },
  "links": {
    "explain": null,
    "next": null,
    "self": "/v1/glossary/index"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": null,
    "request_id": "01M0F5Z2VVACNETA2QD3TCW6T4",
    "source_freshness": {},
    "warnings": []
  }
};

export const glossaryTermsEnvelope = {
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
      "aliases": [],
      "domain_tags": [
        "serving",
        "quality"
      ],
      "highlightable": true,
      "short_definition": "What kind of number this is: observed, allocated, modelled or assumed.",
      "term": "Granularity",
      "term_id": "gt_granularity"
    },
    {
      "aliases": [],
      "domain_tags": [
        "production",
        "governance"
      ],
      "highlightable": true,
      "short_definition": "The stated rule for what counts as the modelling liquid.",
      "term": "Liquids policy",
      "term_id": "gt_liquids_policy"
    },
    {
      "aliases": [],
      "domain_tags": [
        "identity",
        "geospatial"
      ],
      "highlightable": false,
      "short_definition": "The physical hole. One API-10 may have several - an original plus sidetracks, or several laterals.",
      "term": "Wellbore",
      "term_id": "gt_wellbore"
    }
  ],
  "links": {
    "explain": null,
    "next": null,
    "self": "/v1/glossary"
  },
  "meta": {
    "as_of": {
      "requested": "latest",
      "resolved": null
    },
    "deprecations": [],
    "labels": {},
    "next_cursor": null,
    "request_id": "01M0F5Z2X8M1045G1T8M0J8N1P",
    "source_freshness": {},
    "warnings": []
  }
};

export const problemBody = {
  "type": "https://glasswell.rpx.sh/v1/errors/lineage_unresolved",
  "title": "Lineage could not be resolved",
  "status": 404,
  "instance": "/v1/explain",
  "request_id": "01M0F5ZG37GQ2QCGYZ5HXBQPHP",
  "detail": "drv_doesnotexist: resolution stopped (unknown_id); last resolvable node none",
  "handle": "drv_doesnotexist",
  "last_resolved": null,
  "stop_reason": "unknown_id"
};

export function stubFetch(
  routes: Record<string, unknown>,
): (input: RequestInfo | URL) => Promise<Response> {
  return (input: RequestInfo | URL) => {
    const url = String(input);
    for (const [path, body] of Object.entries(routes)) {
      if (url.startsWith(path)) {
        if (body === problemBody) {
          return Promise.resolve(
            new Response(JSON.stringify(body), {
              status: 404,
              headers: { "content-type": "application/problem+json" },
            }),
          );
        }
        return Promise.resolve(
          new Response(JSON.stringify(body), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        );
      }
    }
    return Promise.resolve(new Response("{}", { status: 404 }));
  };
}
