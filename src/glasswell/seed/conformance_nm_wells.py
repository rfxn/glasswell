"""New Mexico well-header conformance rules: the mapping decisions the spine needs (R8).

The 79 NM rules already resident cover fetch, parse and the production spine. None of them
decides anything about a *well header*: there is no identity rule for `wellhistory`, no header
field mapping, no datum rule, no geometry provenance and no statement of what New Mexico's pool
grain means for a served figure. Every one of those is a cross-source mapping decision, so it is
a row here before an executor reads it, not a literal in `ingest/nm_wells.py`.

Two measurements underlie most of these rows, taken by streaming the sealed 2026-08-20
`wellhistory` artifact end to end — first by the planner, then independently again while these
rules were written, with every figure reproduced.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

from glasswell.seed.jurisdictions import RESTATED_ON
from glasswell.seed.supersession import CORRECTED_REFERENCE, correcting_module_function

# Valid time: the decisions describe the 2026-08-20 artifact, which is the date the rest of the
# NM registry dates from. Knowledge time is the publication row, 2026-08-30, and is independent.
EFFECTIVE_FROM = date(2026, 8, 20)
# The status supersession describes a codebook, not the artifact, and dates from the day
# that codebook entered evidence.
STATUS_EFFECTIVE_FROM = date(2026, 9, 1)
# The rollup supersession describes what glasswell serves rather than what the OCD filed, and
# dates from the day the sum was measured against the filings it is a sum of.
ROLLUP_EFFECTIVE_FROM = date(2026, 9, 3)

# The rollup, measured read-only on the deployed spine on 2026-09-04 over
# canonical.production_monthly's New Mexico well_completion_pool rows. Named here rather than
# spelled inside the rationale, so the rule and the mart's own exit read one set of numbers.
POOL_FILINGS = 17597960
POOL_ENTITY_KEYS = 80623
ROLLUP_ROWS = 15387002
ROLLUP_API10S = 70024
ROLLUP_FIRST_MONTH = "2015-01"
ROLLUP_LAST_MONTH = "2026-07"
ROLLUP_SINGLE_POOL_ROWS = 13442637
ROLLUP_MULTI_POOL_ROWS = 1944365
ROLLUP_INPUT_DERIVATIONS = 139

OCD_FTP_PAGE_URL = "https://wwwapps.emnrd.nm.gov/OCD/OCDPermitting/Data/Download.aspx"
OCD_FTP_DESCRIPTIONS_URL = (
    "https://wwwapps.emnrd.nm.gov/OCD/OCDPermitting/Data/DataDownloadDescriptions.aspx"
)

# Both scans agree, record for record, over all 321,510 records of the 2026-08-20 artifact.
RECORDS_MEASURED = 321510
USABLE_PAIRS = 318720
COORDINATE_ABSENT = 1893
COORDINATE_SENTINEL = 897
DISTINCT_API10S = 142000
API10S_WITH_A_POINT = 141778

# status and well_typ_cde over the same scan; the key '&#x20;' is the source's own escaped
# single space, which is CHAR padding rather than a code.
STATUS_DOMAIN = {
    "A": 206195, "P": 50211, "N": 36615, "C": 17400, "H": 4762, "T": 2512, "Q": 1652,
    "E": 733, "S": 506, "J": 486, "X": 331, "Z": 62, "D": 34, "&#x20;": 6, "I": 5,
}
# The OCD data dictionary, sheet "consolidated code list" rows 57-70, fetched 2026-09-01 and
# byte-stable across independent fetches. It is what cr_nm_wellhistory_status_vocab_1 said it
# was waiting for, and its publication is what lets _2 supersede that refusal.
OCD_DATA_DICTIONARY_URL = (
    "https://www.emnrd.nm.gov/ocd/wp-content/uploads/sites/6/"
    "OCD-Interface-v1.1-Data-Dictionary-Protected.xlsx"
)
OCD_DATA_DICTIONARY_SHA256 = (
    "b95c45d3e4e17f1f0c901f6a83777acacece08dc1c29166a4e8543224ff3c413"
)

# The regulator's own wording. I and J are printed the other way round in the dictionary; the
# decodes here follow the live OCD services, which pair every letter with its label per well.
STATUS_DECODES = {
    "A": "Active",
    "C": "Cancelled",
    "D": "Dry Hole",
    "E": "Temporary Abandonment (expired)",
    "H": "Plugged (not released)",
    "I": "Reclamation Fund Pending",
    "J": "Reclamation Fund Approved",
    "N": "New",
    "P": "Plugged (site released)",
    "Q": "Zone Plugged (permanent)",
    "S": "Shut In",
    "T": "Temporary Abandonment",
    "X": "Never Drilled",
    "Z": "Zone Plugged (temporary)",
}
# Ten codes reach a canonical class. Four are documented and have no equivalent, so they carry
# a registered class of their own rather than a null: an absence with a reason, not a gap.
DOCUMENTED_UNMAPPED_CLASS = "documented_unmapped"
STATUS_CANONICAL_MAP = {
    "A": "active",
    "C": "expired",
    "D": "dry",
    "E": "temporarily_abandoned",
    "H": "plugged",
    "I": DOCUMENTED_UNMAPPED_CLASS,
    "J": DOCUMENTED_UNMAPPED_CLASS,
    "N": "permitted",
    "P": "plugged",
    "Q": DOCUMENTED_UNMAPPED_CLASS,
    "S": "inactive",
    "T": "temporarily_abandoned",
    "X": "expired",
    "Z": DOCUMENTED_UNMAPPED_CLASS,
}
# Wells, not records: canonical.wells is effective-dated and every served surface reads
# wells_latest. Measured on the deployed database on 2026-09-01; it sums to DISTINCT_API10S.
STATUS_DOMAIN_WELLS_LATEST = {
    "A": 54326, "P": 48268, "N": 18176, "C": 17067, "H": 2758, "T": 513, "J": 470,
    "E": 266, "X": 103, "Q": 25, "D": 15, "Z": 9, "I": 4,
}
# The trailing-24-month producing check the ratification asked for, over the A wells only.
ACTIVE_PRODUCING_SHARE = {
    "wells": 54326,
    "with_reported_volume": 49117,
    "window_months": 24,
    "share": "90.4%",
}

WELL_TYPE_DOMAIN = {
    "O": 176989, "G": 116934, "I": 20404, "S": 4383, "C": 1774, "M": 705, "W": 320,
    "&#x20;": 1,
}
# rec_termn_dte over the same full scan of the sealed artifact. 142,000 open rows against
# 142,000 distinct API-10s is one open header per well, and every one of them is that well's
# newest: not a single API-10's latest eff_dte row carries a retirement date, so
# canonical.wells_latest's effective_from ranking cannot surface a header the source retired.
REC_TERMN_MEASURED: dict[str, object] = {
    "open_sentinel_rows": 142000,
    "dated_rows": 179510,
    "empty_rows": 0,
    "distinct_api10": 142000,
    "api10_whose_newest_row_is_terminated": 0,
}

DIRECTIONAL_DOMAIN = {
    "V": 136164, "absent": 133507, "H": 43409, "&#x20;": 5163, "D": 3265, "M": 2,
}

NM_WELLS_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "cr_nm_wellhistory_api10_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "conform",
        "rule_kind": "key_composite",
        "applies_to_fields": ["api_st_cde", "api_cnty_cde", "api_well_idn"],
        "spec": {
            "source_cols": ["api_st_cde", "api_cnty_cde", "api_well_idn"],
            "pad": {"api_st_cde": 2, "api_cnty_cde": 3, "api_well_idn": 5},
            "min_width": {"api_st_cde": 2},
            "charset": {
                "api_st_cde": "digits",
                "api_cnty_cde": "digits",
                "api_well_idn": "digits",
            },
            "pad_char": "0",
            "pad_side": "left",
            "separator": "",
            "target_col": "api10",
            "state_code": "30",
            "on_missing": "quarantine",
            "reason_code": "key_incomplete",
            "mirrors_rule_id": "cr_nm_wcproduction_api10_1",
            "measured": {
                "records": RECORDS_MEASURED,
                "distinct_api10": DISTINCT_API10S,
                "over_wide_api_well_idn": 0,
            },
        },
        "rule": (
            "The header API-10 is state code 30, the county code padded to three and the well"
            " number padded to five, concatenated as SSCCCUUUUU — the same composition the"
            " production spine uses, per segment."
        ),
        "rationale": (
            "The header table must key identically to the production spine or the two halves of"
            " New Mexico never join, so this row mirrors cr_nm_wcproduction_api10_1 rather than"
            " restating it in a second idiom. Padding is per segment for the reason that rule"
            " records over 48.1M rows: concatenating first and padding the result gives"
            " '30'+'1'+'5005' -> 0030105005, not 3000105005, which is a different well."
            " The one difference from the spine is measured and worth the row: across all"
            " 321,510 header records api_well_idn never exceeds five characters, so this path"
            " raises no key_incomplete, where wcproduction had exactly one over-wide record it"
            " had to refuse. 30 is New Mexico's API state code and not its FIPS code (35), which"
            " is why the prefix is a rule rather than a slice of a field that looks like it"
            " already carries one."
        ),
        "evidence_url": OCD_FTP_PAGE_URL,
        "code_ref": "src/glasswell/ingest/nm_wells.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_effective_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["eff_dte", "rec_termn_dte"],
            "asserts_header": False,
            "effective_from_field": "eff_dte",
            "promoted_to": "canonical.wells.effective_from",
            "unreadable_eff_dte": "quarantine",
            "reason_code": "out_of_range_date",
            "supersession": "by effective_from ordering; canonical.wells carries no valid-time"
            " end column, so no interval is closed and none is served",
            "source_semantics": {
                "rec_termn_dte": "the source's own retirement date for the header record."
                " Staged verbatim and read by nothing: it is not promoted, not stored and not"
                " served, because there is no column for it",
                "open_interval_sentinel": "9999-12-31",
            },
            "measured_eff_dte_range": ["1900-01-01", "2026-08-19"],
            "measured_rec_termn_dte": REC_TERMN_MEASURED,
            "backfill_rows_kept": True,
        },
        "rule": (
            "eff_dte is the header row's valid-time start and the second half of its key."
            " rec_termn_dte is staged verbatim and promoted nowhere: canonical.wells carries no"
            " valid-time end, so a header is superseded by a later effective_from and by nothing"
            " else. A record whose eff_dte will not read has no key and is quarantined as"
            " out_of_range_date rather than dated by default."
        ),
        "rationale": (
            "The staged range runs 1900-01-01 to 2026-08-19. The 1900-01-01 rows are the"
            " regulator's own pre-ONGARD backfill, and they are kept: an effective-dated table is"
            " exactly where a regulator's backfill belongs, and dropping it would make the well's"
            " history start on the day the state's database did."
            " What this row does *not* legislate is worth stating, because an earlier draft of it"
            " did: canonical.wells has one valid-time column and it is effective_from. There is"
            " no effective_to to translate the 9999-12-31 sentinel into, so the sentinel is"
            " neither stored nor rewritten and rec_termn_dte reaches no canonical column."
            " canonical.wells_latest ranks on effective_from alone, so a header the source had"
            " retired would be served as current if it were also the newest. Measured over all"
            " 321,510 records rather than assumed: 142,000 rows carry the 9999-12-31 open"
            " sentinel against 142,000 distinct API-10s, 179,510 carry a real retirement date"
            " and none is empty — one open header per well — and the number of wells whose"
            " newest row is a retired one is zero. The ranking has nothing to hide today. A"
            " source that begins retiring its newest header is a superseding rule with a column"
            " behind it, not a silent change of meaning here."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "code_ref": "src/glasswell/ingest/nm_wells.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_status_vocab_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["status"],
            "asserts_header": False,
            "promoted_to": "status_reported",
            "status_canonical": None,
            "mapping_table": None,
            "measured_domain": STATUS_DOMAIN,
            "measured_rows": RECORDS_MEASURED,
            "blank_is_data": True,
            "follows_rule_id": "cr_nm_wchistory_status_domain_1",
        },
        "rule": (
            "wellhistory.status has fifteen values and they are promoted verbatim as"
            " status_reported. status_canonical stays null because no codebook maps them."
        ),
        "rationale": (
            "Measured over all 321,510 header records: A 206,195, P 50,211, N 36,615, C 17,400,"
            " H 4,762, T 2,512, Q 1,652, E 733, S 506, J 486, X 331, Z 62, D 34, a single space"
            " 6 and I 5. The counts sum to the record count exactly, so the domain is closed"
            " rather than sampled. Measuring a domain does not produce a mapping: the OCD"
            " publishes no codebook for these letters, and guessing that A is active would put"
            " an unlabelled estimate in the status column — the R8 violation this registry"
            " exists to prevent. cr_nm_wchistory_status_domain_1 already ruled exactly this way"
            " for the completion table's own status code, and lineage.nm_status_map stays empty"
            " for the same reason. So an NM well carries its letter in status_reported and null"
            " in status_canonical: an absent mapping, not a mapping to null. That is why the"
            " served status summary counts every New Mexico well as unmapped, and why this row is"
            " the rule that figure cites — an unmapped count with a rule behind it is a"
            " measurement; without one it is a naked number."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "code_ref": "src/glasswell/ingest/nm_wells.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_status_vocab_2",
        "supersedes_rule_id": "cr_nm_wellhistory_status_vocab_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "conform",
        "rule_kind": "vocab_map",
        "applies_to_fields": ["status"],
        "effective_from": STATUS_EFFECTIVE_FROM,
        "spec": {
            "mapping_table": "nm_wellhistory_status_map",
            "key_col": "status",
            "value_col": "status_canonical",
            "unmapped_action": "passthrough",
            "resolved_at": "read_time",
            "resolver_view": "canonical.status_resolution",
            "promoted_to": "status_reported",
            "writes_canonical_column": False,
            "published_decodes": STATUS_DECODES,
            "canonical_mapping": STATUS_CANONICAL_MAP,
            "documented_without_equivalent": ["I", "J", "Q", "Z"],
            "documented_without_equivalent_class": DOCUMENTED_UNMAPPED_CLASS,
            "transposed_in_dictionary": ["I", "J"],
            "measured_domain": STATUS_DOMAIN,
            "measured_rows": RECORDS_MEASURED,
            "measured_domain_wells_latest": STATUS_DOMAIN_WELLS_LATEST,
            "measured_wells": DISTINCT_API10S,
            "active_producing_share": ACTIVE_PRODUCING_SHARE,
            "evidence_sha256": OCD_DATA_DICTIONARY_SHA256,
            "evidence_sheet": "consolidated code list",
            "corroborating_url": (
                "https://gis.emnrd.nm.gov/arcgis/rest/services/OCDView/Wells_Public/"
                "FeatureServer/0"
            ),
        },
        "rule": (
            "Map wellhistory.status onto the canonical status vocabulary through"
            " lineage.nm_wellhistory_status_map, resolved at read time."
            " status_reported keeps the filed letter, canonical.wells.status_canonical stays"
            " null, and the served class is the join."
        ),
        "rationale": (
            "cr_nm_wellhistory_status_vocab_1 refused to map these letters because no codebook"
            " was in evidence, and stated the condition on which it could be superseded. That"
            " condition is met: the OCD publishes a data dictionary on the EMNRD domain, sheet"
            " consolidated code list rows 57 to 70, linked from the OCD data page and"
            " byte-stable across independent fetches. The published domain is fourteen codes"
            " and the measured domain is those same fourteen plus the CHAR padding blank, so"
            " the vocabulary is closed against the regulator list rather than sampled."
            " Ten codes reach a canonical class. Four do not: Q and Z are zone-plugged states"
            " and I and J are reclamation-fund states, and glasswell has no class for a"
            " wellbore whose zones are plugged or for a financial-assurance state. Forcing them"
            " into plugged would strike 508 wells through on a claim the regulator never made,"
            " and collapsing them into the unmapped class would erase the fact that the"
            " regulator did say something, so they carry the registered class"
            " documented_unmapped instead."
            " The dictionary prints I and J the other way round from both live OCD services,"
            " and the services win on a per-well check rather than on frequency: the four wells"
            " carrying I in canonical.wells_latest are exactly the four the public layer labels"
            " Reclamation Fund Pending, and the nine carrying Z are exactly the nine it labels"
            " Zone Plugged (temporary)."
            " Resolution is at read time because canonical.wells is append-only, its promotion"
            " anti-joins on api10 and effective_from, and a re-promotion appends zero rows: the"
            " only backfills available were to invent a valid time the OCD never filed or to"
            " weaken the refusal. unmapped_action is passthrough rather than the quarantine"
            " North Dakota and Montana use, because this rule reads a header table that is the"
            " identity spine production joins to, and quarantining would drop 2,211 records"
            " from it - a larger error than an unmapped status."
            " Measured at the wells_latest grain every served surface reads, 142,000 wells:"
            " A 54,326, P 48,268, N 18,176, C 17,067, H 2,758, T 513, J 470, E 266, X 103,"
            " Q 25, D 15, Z 9 and I 4. N is the mapping worth arguing with. OCD decodes it as"
            " New and its own wchistory sheet decodes the same letter as New, Not Drilled, so"
            " it maps to permitted - yet 7,614 of those 18,176 wells reported volume in the"
            " trailing 24 months, which is the OCD calculated status lagging rather than a"
            " second meaning, and is recorded here so that nobody reads permitted as a claim"
            " that no wellbore exists. A is the opposite case and the one the ratification"
            " asked to be checked: 49,117 of 54,326 A wells reported volume over the same"
            " window, 90.4 percent, so Active is a producing state here and not a records one."
        ),
        "evidence_url": OCD_DATA_DICTIONARY_URL,
        "code_ref": "src/glasswell/marts/nm_wells.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_well_type_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["well_typ_cde"],
            "asserts_header": False,
            "promoted_to": "well_type_reported",
            "canonical_mapping": None,
            "measured_domain": WELL_TYPE_DOMAIN,
            "measured_rows": RECORDS_MEASURED,
        },
        "rule": (
            "well_typ_cde has eight values and is promoted verbatim as well_type_reported;"
            " no canonical well-type class is asserted from it."
        ),
        "rationale": (
            "Measured over all 321,510 records: O 176,989, G 116,934, I 20,404, S 4,383, C"
            " 1,774, M 705, W 320 and a single space once. The column is named for what it is —"
            " the type the operator reported — and canonical.wells stores it under that name, so"
            " promoting it verbatim asserts nothing. Reading I as injection and S as salt water"
            " disposal is the obvious guess and is exactly the guess this registry refuses"
            " without a codebook: Texas needed a twenty-four-row mapping table with a published"
            " manual behind it before it could class an injector, and New Mexico has no such"
            " manual for this column."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "code_ref": "src/glasswell/ingest/nm_wells.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_datum_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "conform",
        "rule_kind": "datum_transform",
        "applies_to_fields": ["latitude", "longitude", "datum"],
        "spec": {
            "source_epsg": 4269,
            "target_epsg": 4326,
            "detect": {
                "column": "datum",
                "value": "NAD83",
                "lat_col": "latitude",
                "lon_col": "longitude",
            },
            "measured_datum_domain": {"NAD83": RECORDS_MEASURED},
            "on_unexpected_datum": "quarantine",
            "reason_code": "unknown_vocab",
        },
        "rule": "Transform the NAD83 header coordinates to EPSG:4326 before they reach storage.",
        "rationale": (
            "datum is the literal NAD83 on 321,510 of 321,510 records — one value, no"
            " mixed-datum case, so the transform is unconditional rather than per row. Storage"
            " is always 4326 and the transform is recorded as a derivation even though the shift"
            " is sub-metre: no coordinate reaches storage untransformed and unrecorded, which is"
            " the same rule cr_nd_datum_1, cr_blm_plss_datum_1 and cr_nm_c115b_datum_1 state for"
            " their sources. A record arriving under any other datum is quarantined rather than"
            " assumed, because the measurement that makes this rule unconditional is a"
            " measurement of one artifact and not a promise about the next one."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "code_ref": "src/glasswell/ingest/nm_wells.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_coordinate_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "validate",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["latitude", "longitude"],
            "asserts_header": False,
            "unit": "pair",
            "number_format": "scientific",
            "parse": "float",
            "precedence": ["nil", "zero"],
            "outcomes": {
                "promote": "both ordinates non-nil and non-zero",
                "coordinate_absent": "either ordinate nil, checked first",
                "coordinate_sentinel": "neither nil and either ordinate zero",
            },
            "header_is_promoted_regardless": True,
            "measured": {
                "records": RECORDS_MEASURED,
                "usable_pair": USABLE_PAIRS,
                "coordinate_absent": COORDINATE_ABSENT,
                "coordinate_sentinel": COORDINATE_SENTINEL,
                "both_zero": 893,
                "longitude_zero_only": 4,
                "distinct_api10": DISTINCT_API10S,
                "distinct_api10_with_a_point": API10S_WITH_A_POINT,
                "scientific_notation_ordinates": 639237,
                "plain_decimal_ordinates": 0,
            },
        },
        "rule": (
            "A header promotes a surface point only when latitude and longitude are both"
            " non-nil and both non-zero. Either ordinate nil quarantines the geometry as"
            " coordinate_absent; failing that, either ordinate zero quarantines it as"
            " coordinate_sentinel. Nil is checked first. Neither refusal suppresses the well"
            " header."
        ),
        "rationale": (
            "This is a rule about the pair, not about either ordinate, because ST_MakePoint"
            " consumes both and raises on neither. 318,720 of 321,510 records carry a usable"
            " pair, 1,893 carry a nil ordinate and 897 a zero one; the three populations were"
            " counted separately and sum to the record count, so the reconciliation closes on"
            " measurement rather than on subtraction. 141,778 of 142,000 distinct API-10s get at"
            " least one point."
            " The non-obvious part is the longitude: a zero longitude is undetectable by any"
            " range check, because 0.0 is a valid longitude everywhere on Earth. It is a"
            " sentinel here only because New Mexico is not at Greenwich. Four records carry a"
            " good New Mexico latitude and a longitude of exactly zero, and a latitude-only"
            " check would have given those four wells a perfectly valid point in the Gulf of"
            " Guinea, about 9,000 km away, in an append-only table, on a published tile layer."
            " Precedence is nil before zero because three records are mixed — nil on one"
            " ordinate and valued on the other — so two independent per-ordinate rules cannot"
            " express the policy and the order has to be stated rather than left to evaluation."
            " Both ordinates arrive in scientific notation on every record that has one:"
            " 639,237 of 639,237 values, zero plain decimals, so a parser that string-slices or"
            " assumes a decimal point fails on the whole file rather than on a subset."
        ),
        "evidence_url": OCD_FTP_PAGE_URL,
        "code_ref": "src/glasswell/ingest/nm_wells.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_geometry_provenance_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["latitude", "longitude"],
            "asserts_header": False,
            "canonical_column": "geometry_provenance",
            "served_from": "canonical.well_spatial.geom_type",
            "value": "surface",
            "verbatim": True,
            "mirrors_rule_id": "cr_nd_geometry_provenance_1",
        },
        "rule": (
            "A New Mexico well's geometry_provenance is its geom_type served verbatim, and the"
            " only geom_type this source produces is surface."
        ),
        "rationale": (
            "geometry_provenance is a served field, so it needs a rule to cite in New Mexico for"
            " the same reason it needed one in North Dakota: without it the API resolves every"
            " state's provenance to cr_nd_geometry_provenance_1 and a New Mexico figure carries"
            " a North Dakota handle. The value is not derived — it is the geom_type column, and"
            " saying so is the whole content of the rule, which is what makes it checkable."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "code_ref": "src/glasswell/api/routers/wells.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_geometry_scope_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["directional_status"],
            "asserts_header": False,
            "geom_types_produced": ["surface"],
            "geom_types_absent": ["lateral", "bottomhole", "survey_trace"],
            "measured_directional_status": DIRECTIONAL_DOMAIN,
            "measured_rows": RECORDS_MEASURED,
            "corroborating_source": "nm_ocd_wells_gis (esriGeometryPoint, surface only)",
        },
        "rule": (
            "No in-scope New Mexico source ships a lateral or a bottomhole. New Mexico geometry"
            " is a surface point and nothing else, whatever a well's directional status says."
        ),
        "rationale": (
            "directional_status is measured over all 321,510 records as V 136,164, absent"
            " 133,507, H 43,409, a single space 5,163, D 3,265 and M 2 — so 43,409 horizontal"
            " and 3,265 directional wells are present in the header table and none of them"
            " carries a path. The producing footprint of those 46,674 wells is therefore not"
            " represented at all, and this row exists so that no consumer reads a horizontal"
            " well's presence as evidence of a lateral. The corroborating OCD public wells layer"
            " is esriGeometryPoint and describes itself as the surface drilling location, so"
            " both independent New Mexico sources agree. A New Mexico lateral is"
            " data-unreachable rather than unbuilt, and the two measurements are its evidence."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "code_ref": "src/glasswell/ingest/nm_wells.py",
    },
    {
        "rule_id": "cr_nm_wcproduction_pool_rollup_1",
        "source_id": "nm_ocd_wcproduction",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["entity_type", "reporting_level", "aggregation"],
            "asserts_header": False,
            # The prefix this ruling scopes to, in the key the registry already reads it under:
            # marts/producing.py resolves the states with no well-level series from here rather
            # than from a literal in a serving path.
            "state_code": "30",
            "entity_type": "well_completion_pool",
            "reporting_level": "well_completion_pool",
            "aggregation": None,
            "well_level_rows_promoted": 0,
            "rolls_up_to_the_well": False,
            "well_series_endpoint": "/v1/wells/{api10}/production",
            "pool_series_endpoint": "/v1/wells/{api10}/production/pools",
            "contrasts_rule_id": "cr_nd_pool_rollup_1",
            "measured": {
                "promoted_rows": 17597960,
                "distinct_entity_key": 80623,
                "distinct_api10": 70024,
                "distinct_pools": 2596,
                "entity_type_well_rows": 0,
            },
        },
        "rule": (
            "New Mexico production is filed and promoted at the well-completion-pool grain and"
            " glasswell performs no rollup to the well. A New Mexico well's series is its pool"
            " series; the well-level series is absent, not zero."
        ),
        "rationale": (
            "North Dakota's cr_nd_pool_rollup_1 answers the same question the opposite way, and"
            " the contrast is the point: ND promotes one row per pool plus a well total"
            " disclosed as sum_over_pools, so an ND well card can show a well-level series. All"
            " 17,597,960 New Mexico rows are entity_type well_completion_pool with a null"
            " aggregation and there is not one entity_type = well row among them, measured"
            " directly. Summing them here would be a rollup this registry has not decided:"
            " New Mexico's 80,623 entities span 70,024 wells, so 10,599 wells filed in more than"
            " one pool, and adding those filings would need the days-produced treatment and the"
            " null-semantics treatment that cr_nd_pool_rollup_1 spells out and that nobody has"
            " measured for this source. The consequence is a served one and must be disclosed"
            " rather than rendered as an empty chart: an empty well-level series reads as"
            " nothing produced, which is the failure DIR-3 names, so the well production surface"
            " cites this row and points at the pool surface instead. The pool surface's own"
            " aggregation_rule link cites this row too, because what it has to say about a New"
            " Mexico pool series is that no aggregation produced it."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "code_ref": "src/glasswell/api/routers/production.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_basin_scope_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "conform",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["basin"],
            "asserts_header": False,
            "canonical_column": "canonical.wells.basin",
            "assigned": None,
            "registry_basins": ["williston", "permian"],
            "storage_epsg_unaffected": 4326,
            "consequence": "served basin is null and /v1/wells/status-summary carries a"
            " (basin null, state_code 30) bucket",
        },
        "rule": (
            "New Mexico headers carry no basin. The column is left null rather than assigned,"
            " because this build delineates no New Mexico play boundary."
        ),
        "rationale": (
            "North Dakota sets williston and Texas sets permian, and each is defensible because"
            " the slice behind it is scoped to that basin — Texas's by"
            " cr_tx_county_scope_1's 55 Permian-district counties. New Mexico's header table is"
            " the whole state: its wells sit in the Permian in the southeast and the San Juan in"
            " the northwest, and nothing in this build draws the line between them. Writing"
            " permian would be a claim about geography made by a default, on wells the OCD"
            " itself does not classify that way, and it would be wrong for every San Juan well."
            " Null is the honest value, and this row exists so that it is a decision with a"
            " reason rather than a column somebody forgot. Nothing downstream breaks on it:"
            " _basins groups on (basin, state_code) and sorts nulls, and the basin lookup the"
            " well card makes is for storage_epsg, which is 4326 for every registered basin."
            " A New Mexico play delineation is a superseding row with a boundary behind it."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "code_ref": "src/glasswell/ingest/nm_wells.py",
    },
    {
        "rule_id": "cr_nm_wellhistory_header_precedence_1",
        "source_id": "nm_ocd_wellhistory",
        "stage": "join",
        "rule_kind": "code_ref",
        "applies_to_fields": ["api10", "effective_from", "status_reported", "geom"],
        "spec": {
            "module_function": "glasswell.ingest.nm_wells:promote",
            "version": "1",
            "authority": {
                "identity": "nm_ocd_wellhistory",
                "effective_dating": "nm_ocd_wellhistory",
                "status_reported": "nm_ocd_wellhistory",
                "well_type_reported": "nm_ocd_wellhistory",
                "surface_point": "nm_ocd_wellhistory",
            },
            "second_source": None,
            "superseded_when": "the GIS parity is measured (cr_nm_wells_gis_parity_1)",
            "contract_note": (
                "one source, so every field resolves to it; a second source changes this to a"
                " per-field decision through a superseding row, never through an ordering in the"
                " promoter"
            ),
        },
        "rule": (
            "The FTP header table is the sole authority for every New Mexico header field,"
            " including the surface point, until a second source has been measured against it."
        ),
        "rationale": (
            "New Mexico will have two independent measurements of the same well population: the"
            " frozen 2026-08-20 FTP header archive and the daily-refreshed OCD public wells"
            " layer. Which one wins per field is a cross-source mapping decision, so it is a row"
            " rather than an ordering in a promoter. It is seeded with a single authority"
            " because that is the true state before the parity is measured, and it is superseded"
            " by _2 once it is — a changed decision is a new row, never an edit."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "code_ref": "src/glasswell/ingest/nm_wells.py",
    },
)

# The rollup this train registers. It supersedes _1 and contradicts nothing it said:
# rolls_up_to_the_well stays false, because that is a fact about the OCD's filings and about
# canonical, and neither moved. What is added is that glasswell now performs the sum in the
# mart layer and discloses it as one.
POOL_ROLLUP_2: dict[str, object] = {
    "rule_id": "cr_nm_wcproduction_pool_rollup_2",
    "supersedes_rule_id": "cr_nm_wcproduction_pool_rollup_1",
    "source_id": "nm_ocd_wcproduction",
    "stage": "conform",
    "rule_kind": "code_ref",
    "applies_to_fields": ["volume", "days_produced", "null_semantics"],
    "effective_from": ROLLUP_EFFECTIVE_FROM,
    "spec": {
        "state_code": "30",
        "entity_type": "well_completion_pool",
        "reporting_level": "well_completion_pool",
        # Unchanged from _1, and the reason this is not a contradiction: canonical still holds
        # no per-well New Mexico filing, because the OCD made none.
        "rolls_up_to_the_well": False,
        "promotes_to_canonical": False,
        "served_rollup": "sum_over_pools",
        "served_from": "marts.well_pool_rollup",
        "module_function": "glasswell.marts.well_pool_rollup:refresh_well_pool_rollup",
        "source_is_filing_anchor": False,
        "volume": "exact sum over the pool filings of the well-month-stream",
        "days_produced": "maximum over the pool filings, never the sum",
        "null_semantics": "reported and reported_zero are summed; a withheld or absent filing"
        " is not a number to add, and a well-month-stream with none of the first two carries no"
        " mart row rather than a zero",
        "streams_summed": {"oil": "liquid", "gas": "gas", "water": "water"},
        "liquids_basis_rule_id": "cr_nm_wcproduction_liquids_1",
        "contract_note": "the sum is performed in the mart layer and disclosed as a sum;"
        " canonical holds no per-well New Mexico filing and this rule promotes none, and the"
        " pool filings stay the record the series says it is summed from",
        "handle_granularity": "one derivation per refresh, not one per month",
        "selector": "col, api10 and pm, so a point addresses itself under a shared derivation",
        "well_series_endpoint": "/v1/wells/{api10}/production",
        "pool_series_endpoint": "/v1/wells/{api10}/production/pools",
        "contrasts_rule_id": "cr_nd_pool_rollup_1",
        "measured": {
            "pool_filings": POOL_FILINGS,
            "distinct_entity_key": POOL_ENTITY_KEYS,
            "entity_type_well_rows": 0,
            "rollup_rows": ROLLUP_ROWS,
            "distinct_api10": ROLLUP_API10S,
            "first_month": ROLLUP_FIRST_MONTH,
            "last_month": ROLLUP_LAST_MONTH,
            "rows_restating_one_filing": ROLLUP_SINGLE_POOL_ROWS,
            "rows_summing_two_or_more": ROLLUP_MULTI_POOL_ROWS,
            "input_derivations": ROLLUP_INPUT_DERIVATIONS,
            "filings_not_admitted": 0,
        },
    },
    "rule": (
        "A New Mexico well's served monthly series is the exact sum of its completion-pool"
        " filings, read from marts.well_pool_rollup and disclosed as a sum. The OCD filed no"
        " per-well number and canonical holds none."
    ),
    "rationale": (
        "cr_nm_wcproduction_pool_rollup_1 recorded that New Mexico files below the well and"
        " that glasswell performs no rollup, and the second half of that is what changes here:"
        " the filings are the same, canonical is the same, and what is added is a sum glasswell"
        " performs and says it performs. It is not promoted into canonical, because a well row"
        " glasswell computed would have to invent a valid time the regulator never filed at;"
        " it is not summed in the client, which would be a served-looking figure with no"
        " derivation; and it is not a view, because a sum over rows carrying different"
        " derivation ids has no single handle for a point to resolve. A mart reads canonical"
        " and writes marts, carries its own derivation, and is the only layer this can sit in."
        " Measured read-only on the deployed spine on 2026-09-04: 17,597,960 pool filings over"
        " 80,623 completion pools and 70,024 API-10s sum to 15,387,002 well-month-stream rows"
        " over the same 70,024 wells, months 2015-01 to 2026-07, of which 13,442,637 (87.4 per"
        " cent) restate a single pool filing and 1,944,365 sum two or more. Volume sums exactly"
        " because the pool filings are disjoint observations of the same wellbore-month; days"
        " do not sum, for the reason cr_nd_pool_rollup_1 gives, because the filings are"
        " concurrent and a well cannot produce more days than the month holds. The handle is"
        " one per refresh rather than one per month, which is coarser than North Dakota's and"
        " is stated wherever the series is served; the refresh cites all 139 input derivations"
        " rather than an opaque scope, and the selector carries col, api10 and pm so a point"
        " still addresses itself. Every derivation that cites _1 goes on citing it, and the"
        " pool surface is unchanged: the filings stay the record, and the series says it is"
        " their sum."
    ),
    "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
    "code_ref": "src/glasswell/marts/well_pool_rollup.py",
}

# The cadence decision the scheduler registry reads for the rollup mart, declared beside the
# rule it schedules rather than in the scheduler's own module, the shape Texas's takes.
# conformance_schedules.py merges it so one builder writes every cr_job_cadence_<job>_1 row.
NM_CADENCE_DECISIONS: dict[str, dict[str, str]] = {
    "marts_well_pool_rollup": {
        "rule": "Rebuild the per-well rollup after the promotion that writes the pool filings"
        " it sums, never on a clock of its own.",
        "rationale": "The sum is a function of the promoted filings and the vintage they are"
        " read at, so a promotion that moved no row recomputes the same 15,387,002 rows under"
        " the same derivation and republishes nothing. It observes rather than launches,"
        " because the launch posture is the launch flip's own act and this build writes the"
        " second-largest relation in the database.",
    },
}

PROMOTE_MODULE = "glasswell.ingest.nm_wells"

# The correction this train appends. `promote` has never been the name of anything in that
# module; the promoter is `promote_headers`, which `PRECEDENCE_FAMILY` already resolves to by
# family rather than by id -- so the successor changes what the row says about the code and
# nothing about which code runs.
NM_WELLS_RULES = (
    *NM_WELLS_RULES,
    POOL_ROLLUP_2,
    correcting_module_function(
        next(
            rule
            for rule in NM_WELLS_RULES
            if rule["rule_id"] == "cr_nm_wellhistory_header_precedence_1"
        ),
        module_function=f"{PROMOTE_MODULE}:promote_headers",
        effective_from=RESTATED_ON,
        rationale=(
            CORRECTED_REFERENCE.format(symbol="promote", module=PROMOTE_MODULE)
            + " This correction consumed _2, so the supersession superseded_when still names --"
            " the GIS parity measurement, cr_nm_wells_gis_parity_1 -- will be"
            " cr_nm_wellhistory_header_precedence_3."
        ),
    ),
)


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


def seed_conformance_nm_wells(connection: psycopg.Connection) -> int:
    """Rule ids are immutable: a change is a new row with supersedes_rule_id (SB-07 §6.2).

    The count is over this module's own ids rather than over a source-id prefix, so it does not
    move when a sibling seeder adds a row under the same prefix.
    """
    rule_ids = [str(rule["rule_id"]) for rule in NM_WELLS_RULES]
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_RULE, [_row(rule) for rule in NM_WELLS_RULES])
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_id = any(%s)",
            (rule_ids,),
        )
        return int(cursor.fetchone()[0])


GIS_SERVICE_URL = "https://gis.emnrd.nm.gov/arcgis/rest/services/OCDView/Wells_Public/FeatureServer"
GIS_LAYER_URL = f"{GIS_SERVICE_URL}/0"
GIS_SOURCE_ID = "nm_ocd_wells_gis"

# All [NET], by anonymous query on 2026-08-30.
GIS_FEATURES = 141916
GIS_DISTINCT_IDS = 141916
GIS_MAX_RECORD_COUNT = 6000

GIS_LICENSE_NOTE = (
    "New Mexico public record served from an ArcGIS FeatureServer with Extract enabled."
    " copyrightText is the attribution string 'Permitting database of the Oil Conservation"
    " Division (OCD) of the New Mexico Energy, Minerals and Natural Resources Department"
    " (EMNRD).' and carries no redistribution clause. Reachability, the 141,916 feature count,"
    " the uniqueness of id over all of them and the empty terms verified by anonymous query"
    " 2026-08-30."
)

NM_WELLS_GIS_SOURCES: tuple[dict[str, object], ...] = (
    {
        "source_id": GIS_SOURCE_ID,
        "name": "NM OCD Oil and Gas Wells, public surface locations (FeatureServer layer 0)",
        "jurisdiction": "NM",
        "license_note": GIS_LICENSE_NOTE,
        "redistributable": True,
    },
)

NM_WELLS_GIS_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "cr_nm_wells_gis_source_1",
        "source_id": GIS_SOURCE_ID,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["id", "latitude", "longitude", "status", "ulstr"],
            "asserts_header": False,
            "service_url": GIS_SERVICE_URL,
            "layer_id": 0,
            "layer_name": "New Mexico Oil and Gas Wells",
            "where": "1=1",
            "grain": "one point per permitted well surface drilling location",
            "geometry_type": "esriGeometryPoint",
            "capabilities": "Query,Sync,Extract,ChangeTracking",
            "max_record_count": GIS_MAX_RECORD_COUNT,
            "standard_max_record_count": 32000,
            "supports_pagination": True,
            "measured_2026_08_30": {"features": GIS_FEATURES, "distinct_id": GIS_DISTINCT_IDS},
            "terminus": "staging",
        },
        "rule": (
            "Capture the whole OCDView/Wells_Public layer 0 on every pass, and stop at staging:"
            " the parity measurement decides whether and how it promotes."
        ),
        "rationale": (
            "This is a second, independent measurement of the same well population the OCD FTP"
            " header archive carries, and that is the whole reason to take it. The archive is a"
            " frozen 2026-08-20 snapshot; this layer is refreshed as permits are approved, so"
            " the two disagree by construction and the disagreement is measurable rather than"
            " rhetorical. The host is already on the allowlist for the C-115B source, so no"
            " blueprint amendment is required. The whole layer is taken on every pass rather"
            " than a changed slice, because ChangeTracking is advertised but the layer publishes"
            " no field this repository has verified as a reliable change stamp, and a wrong"
            " change filter loses rows silently. Staging is the terminus on purpose: promoting"
            " before the parity is measured would make the parity rule a rationalisation of a"
            " choice already made."
        ),
        "evidence_url": GIS_LAYER_URL,
        "code_ref": "src/glasswell/ingest/nm_wells_gis.py",
    },
    {
        "rule_id": "cr_nm_wells_gis_walk_order_1",
        "source_id": GIS_SOURCE_ID,
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["id"],
            "asserts_header": False,
            "order_by": "id ASC",
            "rejected_order": "OBJECTID ASC",
            "reason": "objectid_is_not_an_identity_on_a_view_backed_layer",
            "tripwire": {
                "reason_code": "duplicate_row",
                "note": "a repeated id inside one harvest means the walk order stopped being"
                " total, not that the regulator filed twice",
            },
            "measured_2026_08_30": {
                "features": GIS_FEATURES,
                "distinct_id": GIS_DISTINCT_IDS,
                "id_is_unique": True,
            },
        },
        "rule": "Walk the layer ordered by id — never by OBJECTID.",
        "rationale": (
            "`resultOffset` re-runs the query for every page, so a walk ordered by anything less"
            " than a total order silently re-reads and skips rows while every count still"
            " reconciles. id is unique over all 141,916 features — the distinct count and the"
            " row count are the same number, asked separately — so ordering on it makes the"
            " pages contiguous and disjoint. OBJECTID is refused for the reason"
            " cr_nm_c115b_walk_order_1 records on the sibling service: on a view-backed layer it"
            " is assigned per query and is not an identity. The duplicate_row quarantine is the"
            " standing tripwire if id ever stops being unique."
        ),
        "evidence_url": GIS_LAYER_URL,
        "code_ref": "src/glasswell/ingest/nm_wells_gis.py",
    },
    {
        "rule_id": "cr_nm_wells_gis_api10_1",
        "source_id": GIS_SOURCE_ID,
        "stage": "parse",
        "rule_kind": "key_composite",
        "applies_to_fields": ["id"],
        "spec": {
            "module_function": "glasswell.ingest.nm_wells_gis:api10_from_dashed",
            "version": "1",
            "source_cols": ["id"],
            "target_col": "api10",
            "source_form": "SS-CCC-NNNNN",
            "target_form": "SSCCCNNNNN",
            "separators_stripped": ["-"],
            "reason_code": "key_incomplete",
            "consistent_with_migration": "054_api10_identity_separators",
        },
        "rule": (
            "Normalise the dashed id (30-001-00505) to the undashed API-10 that is the identity"
            " spine; an id that is not exactly 2-3-5 digits is held, never padded or truncated"
            " into one."
        ),
        "rationale": (
            "Two New Mexico sources ship the API number two ways: the FTP header table ships it"
            " as three unpadded segments and this layer ships it dashed, so both cross a mapping"
            " on the way to the spine and both are rows rather than a strip() in a parser."
            " Migration 054 is the precedent this must be consistent with: separators are"
            " stripped from a well-formed identity and never inferred into one. Strictness costs"
            " nothing today and is the point on the day it does — stripping non-digits from a"
            " 14-character API-14 would silently key a wellbore onto its well, and zero-padding"
            " a short id would build a syntactically perfect API-10 for a well that does not"
            " exist. Refusal to key is key_incomplete, the code migration 021 added for this"
            " exit."
        ),
        "evidence_url": GIS_LAYER_URL,
        "code_ref": "src/glasswell/ingest/nm_wells_gis.py",
    },
    {
        "rule_id": "cr_nm_wells_gis_datum_1",
        "source_id": GIS_SOURCE_ID,
        "stage": "parse",
        "rule_kind": "datum_transform",
        "applies_to_fields": ["latitude", "longitude"],
        "spec": {
            "source_epsg": 4269,
            "target_epsg": 4326,
            "detect": {
                "service_sr_wkid": 4269,
                "lat_col": "latitude",
                "lon_col": "longitude",
            },
            "read_from": "layer json on every fetch, recorded on the manifest",
        },
        "rule": "Transform the NAD83 well points to EPSG:4326 before they reach storage.",
        "rationale": (
            "The layer's own spatialReference is wkid 4269 and latestWkid 4269, read from the"
            " layer JSON on every fetch and recorded on the manifest, so a service that silently"
            " re-projects is a mismatch the fetch raises rather than a shift that lands. Storage"
            " is always 4326 and the transform is recorded as a derivation even though the shift"
            " is sub-metre — the same rule cr_nd_datum_1, cr_nm_c115b_datum_1 and"
            " cr_nm_wellhistory_datum_1 state for their own sources."
        ),
        "evidence_url": GIS_LAYER_URL,
    },
    {
        "rule_id": "cr_nm_wells_gis_parity_1",
        "source_id": GIS_SOURCE_ID,
        "stage": "validate",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "declares_fields": ["id", "latitude", "longitude"],
            "asserts_header": False,
            "form": "prohibition",
            "compared_sources": ["nm_ocd_wells_gis", "nm_ocd_wellhistory"],
            "compared_on": "api10, and the surface point where both carry one",
            "cardinality_measured": {
                "gis_features_2026_08_30": GIS_FEATURES,
                "gis_distinct_api10_2026_08_30": GIS_DISTINCT_IDS,
                "ftp_distinct_api10_2026_08_20": DISTINCT_API10S,
                "ftp_distinct_api10_with_a_point": API10S_WITH_A_POINT,
                "difference_share": "0.06%",
            },
            "distance_distribution_measured": None,
            "on_disagreement": "report both and promote neither",
            "on_present_in_one_source_only": "count and report; never silently drop",
        },
        "rule": (
            "Neither source may be preferred over the other for a New Mexico surface point until"
            " the per-well disagreement has been measured. A well present in one source and"
            " absent from the other is counted and reported, never silently dropped."
        ),
        "rationale": (
            "This is written as a prohibition rather than as an enumerated tolerance because the"
            " evidence for a tolerance does not exist yet. What is measured is the cardinality:"
            " 141,916 distinct API-10s in the GIS layer on 2026-08-30 against 142,000 in the"
            " 2026-08-20 FTP header archive, a 0.06% difference between two independently"
            " produced measurements of the same population — which is the agreement that makes"
            " the comparison worth making at all. What is not measured is the per-well surface"
            " point distance distribution, and until it is, no rule can say which source wins"
            " where they differ. Recording a tolerance now would be an assertion wearing a"
            " measurement's clothes, and cr_nm_wellhistory_header_precedence_1 accordingly still"
            " names the FTP archive as sole authority; the superseding row that changes that is"
            " the one this measurement is for. Both populations move: the GIS layer gains a"
            " point when an APD is approved, and the FTP archive is frozen, so a difference is"
            " expected and its size is the finding."
        ),
        "evidence_url": GIS_LAYER_URL,
        "code_ref": "src/glasswell/ingest/nm_wells_gis.py",
    },
)

_INSERT_SOURCE = """
insert into lineage.sources (source_id, name, jurisdiction, license_note, redistributable)
values (%(source_id)s, %(name)s, %(jurisdiction)s, %(license_note)s, %(redistributable)s)
on conflict do nothing
"""


def seed_sources_nm_wells_gis(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_SOURCE, NM_WELLS_GIS_SOURCES)
    return len(NM_WELLS_GIS_SOURCES)


def seed_conformance_nm_wells_gis(connection: psycopg.Connection) -> int:
    """The GIS layer's own source row and its five rules. Counted over its own ids."""
    seed_sources_nm_wells_gis(connection)
    rule_ids = [str(rule["rule_id"]) for rule in NM_WELLS_GIS_RULES]
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT_RULE, [_row(rule) for rule in NM_WELLS_GIS_RULES])
        cursor.execute(
            "select count(*) from lineage.conformance_rules where rule_id = any(%s)",
            (rule_ids,),
        )
        return int(cursor.fetchone()[0])
