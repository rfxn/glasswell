// Recorded from the tracked `tests/support/serve_branch.py` harness by
// `scripts/record-explorer-fixtures.py`, not hand-written from the router source.
//
// Every glossary term the served document binds to a parameter is keyed by the path the pane's
// `explain()` reads. Request ids are normalized D3 metadata; the owner key is never written.

export const glossaryBodies: Record<string, unknown> = {
  "/v1/glossary/gt_conformance_rule": {
    "data": {
      "aliases": [],
      "appears_in": [
        {
          "kind": "api_field",
          "ref": "/v1/conformance/{rule_id}#/rule_id"
        }
      ],
      "domain_tags": [
        "lineage",
        "data-model",
        "governance"
      ],
      "effective_from": "2026-08-21",
      "expanded_definition": "Rules are served as data, not buried in code: a mapping that exists only in a parser fails review. Each rule declares the stage it runs at, the kind of transform it is, and what happens to a row it cannot resolve.",
      "first_surfaced_in": null,
      "highlightable": true,
      "related_terms": [
        "Quarantine",
        "Effective date",
        "Canonical"
      ],
      "short_definition": "A recorded cross-source mapping decision with its rationale, evidence and effective dates.",
      "source_refs": [
        "blueprint-v0.6 §9",
        "SB-07 §6"
      ],
      "term": "Conformance rule",
      "term_id": "gt_conformance_rule"
    },
    "links": {
      "explain": null,
      "next": null,
      "self": "/v1/glossary/gt_conformance_rule"
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
  },
  "/v1/glossary/gt_county_at_permit": {
    "data": {
      "aliases": [
        "County code at permit"
      ],
      "appears_in": [],
      "domain_tags": [
        "identity",
        "geospatial"
      ],
      "effective_from": "2026-08-21",
      "expanded_definition": "Digits 3-5 of the API-10 are this county, and they stay what they were on the day the permit was filed. A lateral routinely crosses a county line, counties get re-drawn, and a well can be re-permitted, so grouping production by this code tells you where the paperwork went rather than where the rock is. It is a permit fact, and it is the only county most free regulator files publish.",
      "first_surfaced_in": null,
      "highlightable": false,
      "related_terms": [
        "API-10 / API-12 / API-14",
        "PLSS"
      ],
      "short_definition": "The county a well was permitted in, frozen at permit time and carried inside its API number.",
      "source_refs": [
        "canonical.wells.county_code_at_permit",
        "SB-08 §7.1 O-6"
      ],
      "term": "County at permit",
      "term_id": "gt_county_at_permit"
    },
    "links": {
      "explain": null,
      "next": null,
      "self": "/v1/glossary/gt_county_at_permit"
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
  },
  "/v1/glossary/gt_crs_compute_crs": {
    "data": {
      "aliases": [
        "CRS",
        "Compute CRS"
      ],
      "appears_in": [
        {
          "kind": "api_field",
          "ref": "/v1/wells/{api10}#/compute_crs"
        }
      ],
      "domain_tags": [
        "geospatial"
      ],
      "effective_from": "2026-08-21",
      "expanded_definition": "The Williston basin spans UTM 13N and 14N and 97.6 percent of ND laterals lie west of 102W, so no single projected zone is right for the state: measuring them in UTM 14N overstated the fleet by 144,379 ft (fp-audit A3-F1). Lateral length is therefore geodesic on the ellipsoid under cr_nd_compute_crs_2, which chooses no zone. Distance maths in degrees remains a defect, not an approximation - which is why a shapefile's own length field, shipped in degrees, is never served as a length.",
      "first_surfaced_in": null,
      "highlightable": true,
      "related_terms": [
        "Datum",
        "Spacing / spacing unit"
      ],
      "short_definition": "Coordinate reference system. Storage is always EPSG:4326; lateral length is measured geodesically on the WGS84 ellipsoid, and a projected metre-based CRS is used for area and spacing work.",
      "source_refs": [
        "blueprint-v0.6 §9",
        "blueprint-v0.6 §3.0.3"
      ],
      "term": "CRS / compute CRS",
      "term_id": "gt_crs_compute_crs"
    },
    "links": {
      "explain": null,
      "next": null,
      "self": "/v1/glossary/gt_crs_compute_crs"
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
  },
  "/v1/glossary/gt_effective_date": {
    "data": {
      "aliases": [],
      "appears_in": [
        {
          "kind": "api_field",
          "ref": "/v1/wells#/effective_from"
        }
      ],
      "domain_tags": [
        "lineage",
        "time",
        "governance"
      ],
      "effective_from": "2026-08-21",
      "expanded_definition": "Reference data is effective-dated so that a past number can be re-derived under the rules that were in force when it was produced, rather than under today's.",
      "first_surfaced_in": null,
      "highlightable": true,
      "related_terms": [
        "Conformance rule",
        "Knowledge time"
      ],
      "short_definition": "The date from which a rule, alias or reference record applies.",
      "source_refs": [
        "blueprint-v0.6 §9"
      ],
      "term": "Effective date",
      "term_id": "gt_effective_date"
    },
    "links": {
      "explain": null,
      "next": null,
      "self": "/v1/glossary/gt_effective_date"
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
  },
  "/v1/glossary/gt_knowledge_time": {
    "data": {
      "aliases": [],
      "appears_in": [],
      "domain_tags": [
        "lineage",
        "time"
      ],
      "effective_from": "2026-08-21",
      "expanded_definition": "In glasswell the knowledge-time axis is the report vintage, taken from the manifest that the bytes arrived in. A restatement moves a value forward in knowledge time while leaving its valid time untouched.",
      "first_surfaced_in": null,
      "highlightable": true,
      "related_terms": [
        "Valid time",
        "Report vintage",
        "Bitemporal"
      ],
      "short_definition": "When the system learned a fact, as distinct from when the fact happened.",
      "source_refs": [
        "SB-07 §12",
        "DIR-2"
      ],
      "term": "Knowledge time",
      "term_id": "gt_knowledge_time"
    },
    "links": {
      "explain": null,
      "next": null,
      "self": "/v1/glossary/gt_knowledge_time"
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
  },
  "/v1/glossary/gt_operator_of_record": {
    "data": {
      "aliases": [
        "Operator",
        "Operator name reported"
      ],
      "appears_in": [],
      "domain_tags": [
        "identity",
        "data-model"
      ],
      "effective_from": "2026-08-21",
      "expanded_definition": "Served exactly as reported, because tidying the name is a cross-source mapping decision and those are conformance rules with rationales, not string edits inside a parser. So one company appears under several spellings until a rule joins them, and filtering by operator counts filings rather than corporate parents - an acquisition, a name change and a subsidiary all read as separate operators here until the join is recorded.",
      "first_surfaced_in": null,
      "highlightable": false,
      "related_terms": [
        "Conformance rule",
        "Canonical",
        "Spine"
      ],
      "short_definition": "The company the regulator lists as responsible for the well, spelled the way that source spelled it.",
      "source_refs": [
        "canonical.wells.operator_name_reported",
        "SB-08 §7.1 O-6"
      ],
      "term": "Operator of record",
      "term_id": "gt_operator_of_record"
    },
    "links": {
      "explain": null,
      "next": null,
      "self": "/v1/glossary/gt_operator_of_record"
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
  },
  "/v1/glossary/gt_pipeline_stage": {
    "data": {
      "aliases": [
        "Stage"
      ],
      "appears_in": [],
      "domain_tags": [
        "lineage",
        "quality"
      ],
      "effective_from": "2026-08-21",
      "expanded_definition": "The four stages are ordered and a row only reaches one by clearing the ones before it, so the stage is a measure of how far the data got: parse means the bytes would not read at all, join means the row was well-formed and still could not be tied to a well. It is the first thing to group a quarantine backlog by, because the repair is a different job at each stage - a parse failure is usually one file, a join failure is usually one rule.",
      "first_surfaced_in": null,
      "highlightable": false,
      "related_terms": [
        "Conformance rule",
        "Quarantine",
        "Staging"
      ],
      "short_definition": "Which of parse, validate, conform or join a rule runs at, or a rejected row failed at.",
      "source_refs": [
        "SB-07 §6.2",
        "migration 005_conformance.sql",
        "migration 007_quarantine.sql"
      ],
      "term": "Pipeline stage",
      "term_id": "gt_pipeline_stage"
    },
    "links": {
      "explain": null,
      "next": null,
      "self": "/v1/glossary/gt_pipeline_stage"
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
  },
  "/v1/glossary/gt_production_month": {
    "data": {
      "aliases": [
        "pm"
      ],
      "appears_in": [],
      "domain_tags": [
        "production",
        "time"
      ],
      "effective_from": "2026-08-21",
      "expanded_definition": "Every production row carries two dates answering two different questions, and this is the valid-time one. The other is the report vintage, the knowledge date the regulator published it on. A single production month therefore has as many values as it has restatements, and all of them are correct at their own vintage - which is why an axis of production months means nothing until the vintage it was read at is stated beside it.",
      "first_surfaced_in": null,
      "highlightable": false,
      "related_terms": [
        "Report vintage",
        "Valid time",
        "Bitemporal",
        "Restatement"
      ],
      "short_definition": "The month a volume is attributed to - when the oil came out of the ground, not when anyone said so.",
      "source_refs": [
        "canonical.production.production_month",
        "DIR-2"
      ],
      "term": "Production month",
      "term_id": "gt_production_month"
    },
    "links": {
      "explain": null,
      "next": null,
      "self": "/v1/glossary/gt_production_month"
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
  },
  "/v1/glossary/gt_quarantine": {
    "data": {
      "aliases": [],
      "appears_in": [
        {
          "kind": "api_field",
          "ref": "/v1/quarantine#/reason_code"
        }
      ],
      "domain_tags": [
        "quality",
        "lineage"
      ],
      "effective_from": "2026-08-21",
      "expanded_definition": "It has an endpoint, because the kitchen is the product. A zero quarantine rate is read as evidence that the checks are not running, not as evidence that the data is clean.",
      "first_surfaced_in": null,
      "highlightable": true,
      "related_terms": [
        "Conformance rule",
        "Audit stream"
      ],
      "short_definition": "The table of rows that failed promotion, with the reason code, the rule that rejected them, the raw payload and a lifecycle state.",
      "source_refs": [
        "blueprint-v0.6 §9",
        "SB-07 §12"
      ],
      "term": "Quarantine",
      "term_id": "gt_quarantine"
    },
    "links": {
      "explain": null,
      "next": null,
      "self": "/v1/glossary/gt_quarantine"
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
  },
  "/v1/glossary/gt_quarantine_state": {
    "data": {
      "aliases": [],
      "appears_in": [],
      "domain_tags": [
        "quality",
        "governance"
      ],
      "effective_from": "2026-08-21",
      "expanded_definition": "A rejected row is never deleted, so this is how the backlog gets worked rather than cleared. Released means a later rule resolved the row and it was promoted after all; accepted_loss is a deliberate decision to leave data on the floor, and it is the one state that should be read as a claim about the product; superseded means the source itself replaced the row. Counting open alone understates what was rejected and overstates what was fixed.",
      "first_surfaced_in": null,
      "highlightable": false,
      "related_terms": [
        "Quarantine",
        "Conformance rule",
        "Restatement"
      ],
      "short_definition": "Where a rejected row stands: open, released, accepted_loss or superseded.",
      "source_refs": [
        "SB-07 §8",
        "migration 007_quarantine.sql"
      ],
      "term": "Quarantine state",
      "term_id": "gt_quarantine_state"
    },
    "links": {
      "explain": null,
      "next": null,
      "self": "/v1/glossary/gt_quarantine_state"
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
  },
  "/v1/glossary/gt_report_vintage": {
    "data": {
      "aliases": [],
      "appears_in": [
        {
          "kind": "api_field",
          "ref": "/v1/wells/{api10}/production#/series/oil_bbl_report_vintage"
        }
      ],
      "domain_tags": [
        "lineage",
        "time"
      ],
      "effective_from": "2026-08-21",
      "expanded_definition": "A restatement is a new vintage, never an edit. The vintage is taken from the manifest that carried the bytes, so it is a property of the retrieval rather than of the clock the pipeline happened to run on.",
      "first_surfaced_in": null,
      "highlightable": true,
      "related_terms": [
        "Knowledge time",
        "Bitemporal",
        "Restatement",
        "Vintage (well vintage)"
      ],
      "short_definition": "When a value was reported, as distinct from the month it describes.",
      "source_refs": [
        "blueprint-v0.6 §9",
        "DIR-2"
      ],
      "term": "Report vintage",
      "term_id": "gt_report_vintage"
    },
    "links": {
      "explain": null,
      "next": null,
      "self": "/v1/glossary/gt_report_vintage"
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
  },
  "/v1/glossary/gt_rule_kind": {
    "data": {
      "aliases": [],
      "appears_in": [],
      "domain_tags": [
        "lineage",
        "data-model",
        "governance"
      ],
      "effective_from": "2026-08-21",
      "expanded_definition": "The kind is the executor, so it says how to read the rule's spec and what a failure at that rule means. code_ref is the honest exception: the decision is recorded as a row and carried out by named code, which keeps a policy reviewable where an executable spec could not express it. A registry that was all code_ref would be a mapping living in code, wearing a row for cover.",
      "first_surfaced_in": null,
      "highlightable": false,
      "related_terms": [
        "Conformance rule",
        "Datum",
        "Canonical"
      ],
      "short_definition": "What a conformance rule does - unit_conform, vocab_map, alias_join, datum_transform, key_composite, parse_directive, validity_filter or code_ref.",
      "source_refs": [
        "SB-07 §6.2",
        "migration 005_conformance.sql"
      ],
      "term": "Rule kind",
      "term_id": "gt_rule_kind"
    },
    "links": {
      "explain": null,
      "next": null,
      "self": "/v1/glossary/gt_rule_kind"
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
  },
  "/v1/glossary/gt_source": {
    "data": {
      "aliases": [
        "Source id",
        "Source layer"
      ],
      "appears_in": [],
      "domain_tags": [
        "lineage",
        "data-model"
      ],
      "effective_from": "2026-08-21",
      "expanded_definition": "The source id is the join key for most of the kitchen: manifests record whose bytes were fetched, conformance rules are declared against one source, quarantined rows name the source they were read from, and freshness is measured per source rather than for the system as a whole. Two files from one agency are two sources when they are published separately, because they go stale separately and a single freshness number would hide the older one.",
      "first_surfaced_in": null,
      "highlightable": false,
      "related_terms": [
        "Manifest",
        "Raw zone",
        "Conformance rule"
      ],
      "short_definition": "One upstream publication - a specific regulator file or feed - under a stable id.",
      "source_refs": [
        "lineage.sources",
        "SB-08 §7.1 O-6"
      ],
      "term": "Source",
      "term_id": "gt_source"
    },
    "links": {
      "explain": null,
      "next": null,
      "self": "/v1/glossary/gt_source"
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
  },
  "/v1/glossary/gt_stream": {
    "data": {
      "aliases": [],
      "appears_in": [
        {
          "kind": "api_field",
          "ref": "/v1/wells/{api10}/production#/series/gas_mcf"
        }
      ],
      "domain_tags": [
        "production",
        "data-model"
      ],
      "effective_from": "2026-08-21",
      "expanded_definition": "North Dakota's monthly report also carries gas sold and gas flared. Those are dispositions of produced gas rather than streams, so they are recorded and measured but not promoted as production.",
      "first_surfaced_in": null,
      "highlightable": false,
      "related_terms": [
        "Condensate",
        "Mcf",
        "Liquids policy"
      ],
      "short_definition": "Oil, gas, water or condensate - the substance a volume measures.",
      "source_refs": [
        "blueprint-v0.6 §9"
      ],
      "term": "Stream",
      "term_id": "gt_stream"
    },
    "links": {
      "explain": null,
      "next": null,
      "self": "/v1/glossary/gt_stream"
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
  },
  "/v1/glossary/gt_well_name": {
    "data": {
      "aliases": [],
      "appears_in": [],
      "domain_tags": [
        "identity"
      ],
      "effective_from": "2026-08-21",
      "expanded_definition": "A label, never an identity. Names repeat across operators and basins, change when a lease changes hands, and differ between the permit file and the production file for the same hole. Joining on one is how two wells quietly become one well, and it is the reason the spine is API-10 - a name is for reading, a number is for joining.",
      "first_surfaced_in": null,
      "highlightable": false,
      "related_terms": [
        "API-10 / API-12 / API-14",
        "Spine",
        "Operator of record"
      ],
      "short_definition": "The operator's name for a well - usually a lease name and a number - exactly as filed.",
      "source_refs": [
        "canonical.wells.well_name",
        "SB-08 §7.1 O-6"
      ],
      "term": "Well name",
      "term_id": "gt_well_name"
    },
    "links": {
      "explain": null,
      "next": null,
      "self": "/v1/glossary/gt_well_name"
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
  },
  "/v1/glossary/gt_well_status": {
    "data": {
      "aliases": [
        "Status canonical"
      ],
      "appears_in": [],
      "domain_tags": [
        "identity",
        "data-model"
      ],
      "effective_from": "2026-08-21",
      "expanded_definition": "Each regulator publishes its own codes, and every mapping onto this vocabulary is a conformance rule with a rationale - cr_nd_status_vocab_1 in North Dakota, cr_tx_status_vocab_1 in Texas - so a canonical status resolves to the decision that produced it. Empty is not the same as unknown: it means the source reported no status at all, and a code the map does not recognise is quarantined rather than guessed at.",
      "first_surfaced_in": null,
      "highlightable": false,
      "related_terms": [
        "Conformance rule",
        "Confidential well",
        "Quarantine"
      ],
      "short_definition": "The well's lifecycle state mapped to one vocabulary across states - active, plugged, dry, expired, inactive, confidential, permitted, drilling or temporarily_abandoned.",
      "source_refs": [
        "migration 010_nd_reference_seed.sql",
        "migration 027_tx_slice.sql"
      ],
      "term": "Well status",
      "term_id": "gt_well_status"
    },
    "links": {
      "explain": null,
      "next": null,
      "self": "/v1/glossary/gt_well_status"
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
  }
};
