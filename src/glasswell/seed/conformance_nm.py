"""The NM OCD conformance registry (SB-07 §6.2), appended to in phase order.

Phase 1 seeds the retrieval decisions: what the artifact is called, where it comes from, and
why glasswell stamps its own vintage on it. Phase 2 adds the parse decisions: the record tag and
namespace, the encoding, the header each source declares, and the CHAR widths that make a code
look like a code only after a declared trim. Phase 3 adds the promotion decisions: the key, the
stream vocabulary, the units and the policies the spine will cite. Phase 4 adds the four the
promotion itself had to take — the window, the day domain, the collision routing and the volume
floor. Phase 5 adds the completion dimension's, and with them the grouping key D3's Validator B
is built on. Rule ids are immutable — a correction is a new row with `supersedes_rule_id`, never
an edit (R8).

`load_rules` reads one `source_id` per call, so every family is instantiated per source: a row
seeded on `nm_ocd_wcproduction` is invisible to a `nm_ocd_pool` load, and a derivation citing
another source's rule id would be a lineage claim glasswell cannot resolve.

A policy with no executor is a `parse_directive` carrying `asserts_header: false`, not a
`code_ref`: a `code_ref` names a symbol that must resolve (SB-07 §6 contract (a)), and the
functions these policies configure land with the promotion. Such a row declares its fields in
`spec.declares_fields` and leaves `applies_to_fields` at `all`, because a `parse_directive`
whose fields are frame columns is a header assertion, and a header assertion quarantines the
whole batch on the day a later phase projects one of those columns away.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

from glasswell.seed.reference import NM_TABLES

OCD_DATA_URL = "https://www.emnrd.nm.gov/ocd/ocd-data/"
OCD_FTP_PAGE_URL = "https://www.emnrd.nm.gov/ocd/ocd-data/ftp-server/"
OCD_FTP_DESCRIPTIONS_URL = (
    "https://www.emnrd.nm.gov/wp-content/uploads/sites/6/FTPDataSetDescriptions.pdf"
)

EFFECTIVE_FROM = date(2026, 8, 20)
# The promotion decisions were taken against the staged corpus, a day after the pull they read.
PROMOTION_FROM = date(2026, 8, 21)
# DIR-12's window, applied at promotion as a re-runnable predicate (cr_nm_wcproduction_window_1).
PROMOTION_WINDOW_START = date(2015, 1, 1)

FTP_HOST = "164.64.106.6"
FTP_ROOT = "/Public/OCD/OCD Interface v1.1"
# volumes/ carries the measured artifacts, core/ the registries the crosswalk needs.
FTP_SECTIONS: dict[str, str] = {table: "core" for table, _ in NM_TABLES}
FTP_SECTIONS["wcproduction"] = "volumes"

RECORD_NAMESPACE = "urn:schemas-microsoft-com:sql:SqlRowSet1"
RECORD_ENCODING = "utf-16"
BATCH_ROWS = 65536

# The T1-d inventory, measured over every record of every artifact of the 2026-08-20 pull: no
# child is ever absent and no source carries a column this list does not.
NM_COLUMNS: dict[str, tuple[str, ...]] = {
    "wcproduction": (
        "api_st_cde", "api_cnty_cde", "api_well_idn", "pool_idn", "prodn_mth", "prodn_yr",
        "ogrid_cde", "prd_knd_cde", "eff_dte", "amend_ind", "c115_wc_stat_cde", "prod_amt",
        "prodn_day_num", "mod_dte"
    ),
    "wellhistory": (
        "api_st_cde", "api_cnty_cde", "api_well_idn", "eff_dte", "rec_termn_dte",
        "ogrid_cde", "well_name", "prod_prop_idn", "prop_fm_desc", "well_nbr_idn",
        "well_typ_cde", "lease_typ_cde", "ocd_district", "last_apd_status",
        "last_apd_apr_date", "last_apd_cancel_date", "latitude", "longitude", "datum",
        "sdiv_twp_idn", "sdiv_rng_idn", "sdiv_sect_num", "sdiv_unlt_idn", "ocd_unlt_idn",
        "lot_idn", "ftg_ns_num", "ftg_ew_num", "ns_cde", "ew_cde", "status", "spud_dte",
        "plug_dte", "directional_status", "completed_in_adjacent_state", "elev_gl_num",
        "dpth_tgt_num", "dpth_tvd_num", "dpth_mvd_num"
    ),
    "wchistory": (
        "api_st_cde", "api_cnty_cde", "api_well_idn", "pool_idn", "eff_dte",
        "rec_termn_dte", "wc_stat_cde", "ogrid_cde", "spc_unit_idn", "prod_prop_idn",
        "well_nbr_idn", "sdiv_twp_idn", "sdiv_rng_idn", "sdiv_sect_num", "sdiv_unlt_idn",
        "ocd_unlt_idn", "ftg_ns_num", "ftg_ew_num", "ns_cde", "ew_cde", "dpth_perf_top_num",
        "dpth_perf_btm_num", "compl_dte", "fst_oil_prodn_dte", "fst_gas_deliv_dte",
        "tst_dte", "c104_apr_dte", "bh_psd_act_ind", "dhc_cmngl_ind", "dhc_dte",
        "well_typ_cde", "prodn_meth_cde"
    ),
    "podwc": (
        "pod_idn", "api_st_cde", "api_cnty_cde", "api_well_idn", "pool_idn", "eff_dte"
    ),
    "pod": (
        "pod_idn", "pod_typ_cde", "pod_dsc", "ogrid_cde", "api_cnty_cde", "sdiv_twp_idn",
        "sdiv_rng_idn", "sdiv_sect_num", "sdiv_unlt_idn", "fac_typ_cde", "eff_dte"
    ),
    "ogrid": (
        "ogrid_cde", "ogrid_nam", "ogrid_adr_nam", "mail_stop", "line1_adr", "line2_adr",
        "line3_adr", "city_nam", "st_nam", "zip_cde", "ctry_nam", "phone_num", "fax_num",
        "stat_eff_dte", "issng_ag_cde", "lst_modified_dte", "created_dte", "ogrid_stat_cde"
    ),
    "pool": (
        "pool_idn", "eff_dte", "pool_nam", "std_spc_oil_num", "std_spc_gas_num",
        "gor_lim_num", "top_allow_oil_num", "csghd_gas_lim_num", "ft_end_ln_num",
        "ft_side_ln_num", "ft_near_well_num", "ft_qq_ln_num", "acre_basis_num",
        "del_basis_num", "pool_reg_cde", "pool_typ_cde", "dpth_allow_min_num",
        "simult_dedt_yon"
    ),
    "spacingunit": (
        "spc_unit_idn", "eff_dte", "dedt_acre_dec", "pool_idn", "acre_typ"
    ),
    "property": (
        "prod_prop_idn", "eff_dte", "prod_prop_nam", "ogrid_cde", "prod_prop_stat_cde"
    ),
}

# Right-padded CHAR columns and their fixed widths, measured the same way. Every value that ends
# in a space pads to exactly one width per column, which is what makes this padding rather than
# data; leading spaces exist too and are data, so the declared trim is right-side only.
NM_CHAR_WIDTHS: dict[str, dict[str, int]] = {
    "wcproduction": {"prd_knd_cde": 2},
    "wellhistory": {
        "lease_typ_cde": 2, "lot_idn": 6, "prop_fm_desc": 40, "sdiv_rng_idn": 3,
        "sdiv_twp_idn": 3, "sdiv_unlt_idn": 3, "well_nbr_idn": 4
    },
    "wchistory": {"sdiv_unlt_idn": 3, "well_nbr_idn": 4},
    "podwc": {},
    "pod": {"pod_dsc": 40, "sdiv_twp_idn": 10, "sdiv_unlt_idn": 3},
    "ogrid": {
        "city_nam": 30, "ctry_nam": 15, "issng_ag_cde": 5, "line1_adr": 30, "line2_adr": 30,
        "line3_adr": 30, "mail_stop": 20, "ogrid_adr_nam": 30, "ogrid_nam": 44, "st_nam": 2,
        "zip_cde": 9
    },
    "pool": {"pool_nam": 35},
    "spacingunit": {},
    "property": {"prod_prop_nam": 40},
}


def remote_path(table: str) -> str:
    return f"{FTP_ROOT}/{FTP_SECTIONS[table]}/{table}/{table}.zip"


def _undated_vintage(table: str) -> dict[str, object]:
    return {
        "rule_id": f"cr_nm_{table}_undated_vintage_1",
        "source_id": f"nm_ocd_{table}",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["fetch_vintage", "source_key"],
        "spec": {
            "source_key": f"{table}.zip",
            "vintage_source": "run_clock",
            "upstream_mtime_use": "recorded_only",
            "filename_carries_vintage": False,
        },
        "rule": (
            f"{table}.zip is undated, so the retrieval vintage is glasswell's own stamp and the"
            " source_key is the constant filename."
        ),
        "rationale": (
            "The live FTP publishes one undated zip per table and overwrites it in place, so"
            " the artifact's name carries no as-of date and MDTM describes the export job"
            " rather than the knowledge date of the data. DIR-2 makes the vintage a first-class"
            " dimension, so it is stamped from the run clock (SB-06 §3.3) and upstream_mtime is"
            " recorded beside it as evidence, never promoted to it. The source_key stays the"
            " constant filename because the supersession chain is built on"
            " (source_id, source_key): a vintage-stamped key would start a new chain on every"
            " pull and silently break restatement detection."
        ),
        "evidence_url": OCD_FTP_PAGE_URL,
    }


def _ftp_layout(table: str) -> dict[str, object]:
    return {
        "rule_id": f"cr_nm_{table}_ftp_layout_1",
        "source_id": f"nm_ocd_{table}",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["acquisition_url"],
        "spec": {
            "acquisition_method": "ftp_anon",
            "root": FTP_ROOT,
            "section": FTP_SECTIONS[table],
            "path": remote_path(table),
            "member_stream": True,
            "documented_cadence": "monthly, first Monday",
            "observed_cadence": "nightly",
        },
        "rule": (
            f"Retrieve {table} from {FTP_SECTIONS[table]}/{table}/{table}.zip under"
            f" {FTP_ROOT!r}, and treat the published cadence and naming as superseded by the"
            " observed ones."
        ),
        "rationale": (
            "FTPDataSetDescriptions.pdf documents dated bundles (OCDCoreDataYYYYMMDD.zip,"
            " OCDWCVolumesYYYYMMDD.zip) refreshed 'on a monthly basis, the first Monday of"
            " every month'. The live server carries neither: per-table directories holding a"
            " single undated zip, with timestamps of 2026-08-19 22:55 through 2026-08-20 00:22"
            " — a Wednesday, hours before the probe. Documented behaviour is superseded by"
            " observed behaviour, and this row records which is which so a future reader can"
            " tell a drift from a misreading of the PDF."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
    }


def _host_pin(table: str) -> dict[str, object]:
    return {
        "rule_id": f"cr_nm_{table}_host_pin_1",
        "source_id": f"nm_ocd_{table}",
        "stage": "parse",
        "rule_kind": "code_ref",
        "applies_to_fields": ["acquisition_url"],
        "spec": {
            "module_function": "glasswell.ingest.nm_ocd:fetch_table",
            "host": FTP_HOST,
            "port": 21,
            "on_unresolved": "halt",
            "reason_code": "host_unresolved",
            "resolution": "manual re-pin, recorded as an audit event",
            "contract_note": (
                "fetch_table resolves the URL from the pinned host and nothing else. A connect"
                " failure raises FtpHostUnresolved, which fetch_raw records as"
                " raw.fetch_failed reason=host_unresolved and re-raises; no fallback host is"
                " tried and no page is parsed for a new address."
            ),
        },
        "rule": (
            f"The OCD FTP host is pinned to {FTP_HOST}; a move halts the fetch and is re-pinned"
            " by hand."
        ),
        "rationale": (
            "The EMNRD FTP page publishes the address as an image, so there is no machine"
            " -readable source to re-resolve from and any automatic recovery would be a guess"
            " about where public data now lives. SB-01 §1.2 rules that the fetch halts with"
            " raw.fetch_failed reason=host_unresolved; the re-pin is a one-line config change"
            " and an audit event, never a scraper and never OCR."
        ),
        "evidence_url": OCD_DATA_URL,
        "code_ref": "glasswell.ingest.nm_ocd:fetch_table",
    }


def _parse(table: str) -> dict[str, object]:
    return {
        "rule_id": f"cr_nm_{table}_parse_1",
        "source_id": f"nm_ocd_{table}",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {
            "format_pin": "xml",
            "member": f"{table}.xml",
            "member_stream": True,
            "record_tag": table,
            "namespace": RECORD_NAMESPACE,
            "encoding": RECORD_ENCODING,
            "batch_rows": BATCH_ROWS,
            "header_policy": "contains",
            "unexpected_column": "halt",
            "expected_columns": list(NM_COLUMNS[table]),
            "empty_element": "null",
            "source_row_ordinal_base": 0,
        },
        "rule": (
            f"Stream the {table} records out of the zip member as UTF-16 text, matching"
            f" {{{RECORD_NAMESPACE}}}{table}, and stage every child column verbatim."
        ),
        "rationale": (
            "The artifact is a SQL Server SqlRowSet1 dump: UTF-16LE with a BOM, an inline"
            " xsd:schema header, and records that carry the namespace on every element. Both"
            " pins are failure modes that are silent rather than loud — a bare-tag match against"
            " a namespaced document returns zero records and raises nothing, and the encoding is"
            " not declared anywhere in the document. The header is judged per batch against the"
            " column list measured over every record of the 2026-08-20 pull, where no child is"
            " ever absent: a batch that loses a declared column is quarantined as"
            " schema_mismatch rather than staged as a column of nulls, and a column nobody"
            " declared halts the load, because an artifact that grew a field is a change to the"
            " source and not a row to reject. An element with no character"
            " data stages as NULL: XML cannot distinguish <x></x> from <x/>, so the empty string"
            " would be a claim the bytes do not support."
        ),
        "evidence_url": OCD_FTP_PAGE_URL,
    }


def _pad(table: str) -> dict[str, object]:
    widths = NM_CHAR_WIDTHS[table]
    trim = {
        column: {"width": width, "side": "right", "char": " "}
        for column, width in widths.items()
    }
    measured = (
        "No column in this source is right-padded, measured the same way, so the trim is empty"
        " and stays declared rather than assumed."
        if not widths
        else f"The padded columns and their fixed widths are {sorted(widths)}."
    )
    return {
        "rule_id": f"cr_nm_{table}_pad_1",
        "source_id": f"nm_ocd_{table}",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": sorted(widths) or ["all"],
        "spec": {"trim": trim, "staging_is_verbatim": True},
        "rule": (
            f"Values in {sorted(widths) or 'no column of this source'} are CHAR-padded on the"
            " right; the trim is declared here and applied when the value is mapped, never in"
            " the parser."
        ),
        "rationale": (
            "prd_knd_cde is CHAR(2) and arrives as 'O '. An exact-match vocabulary against 'O'"
            " would quarantine every row of the spine as stream_not_promoted while every rule"
            " reported success, so the trim is a mapping decision and gets a rule row rather"
            " than a .strip() in the parser (R8). Which columns pad is measured, not assumed:"
            " every value that ends in a space pads to exactly one width per column, which is"
            " what separates padding from data. Leading spaces occur too and are data, so the"
            f" trim is right-side only. {measured} Staging keeps the padded value, because"
            " staging is the source and the trim belongs to the mapping that reads it."
        ),
        "evidence_url": OCD_FTP_PAGE_URL,
    }


def _mod_dte() -> dict[str, object]:
    return {
        "rule_id": "cr_nm_wcproduction_mod_dte_1",
        "source_id": "nm_ocd_wcproduction",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["mod_dte", "amend_ind"],
        "spec": {
            "change_detection_key": "mod_dte",
            "amendment_flag": "amend_ind",
            "amend_ind_domain": ["N", "Y", "1", "2", "3", "4", "6", "7", "9", "X"],
            "in_value_hash": False,
            "carried_as": "text",
        },
        "rule": (
            "mod_dte and amend_ind are carried verbatim as change signals and neither enters"
            " value_hash."
        ),
        "rationale": (
            "amend_ind is the regulator's own amendment flag and mod_dte is a row-touch"
            " timestamp; SB-01 §5.4 calls mod_dte a promotion optimisation, not a lineage"
            " concept. Folding either into value_hash would make a timestamp bump a restatement"
            " and, at 48.1M rows, manufacture them at a scale nobody could unpick. amend_ind is"
            " a ten-value vocabulary rather than a boolean — N 34,812,326, Y 13,280,514, then"
            " 1, 2, 4, 6, 9, 3, X and 7 across 11,494 rows — so a Y/N reading mis-classifies"
            " every one of them. On a canonical row, mod_dte is the mod_dte of the manifest that"
            " last produced a value change, not the latest observed: change-only append leaves"
            " an unappended row carrying the prior one, and a consumer reading it as freshness"
            " would be wrong."
        ),
        "evidence_url": OCD_FTP_PAGE_URL,
    }


def _month() -> dict[str, object]:
    return {
        "rule_id": "cr_nm_wcproduction_month_1",
        "source_id": "nm_ocd_wcproduction",
        "stage": "parse",
        "rule_kind": "parse_directive",
        "applies_to_fields": ["prodn_yr", "prodn_mth"],
        "spec": {
            "target_field": "production_month",
            "year_field": "prodn_yr",
            "month_field": "prodn_mth",
            "month_is_zero_padded": False,
            "day": 1,
            "semantics": "valid_time",
        },
        "rule": (
            "production_month is prodn_yr and prodn_mth composed with the day pinned to 01;"
            " eff_dte is not the production month."
        ),
        "rationale": (
            "The source carries no month column: prodn_yr is a four-digit year and prodn_mth is"
            " an unpadded integer ('7', not '07'), so the composition is a decision and is"
            " recorded as one. The day is pinned to 01 because the grain is a month and a"
            " month-end date would imply a precision the filing does not have. eff_dte is a"
            " filing effective date and mod_dte a row-touch timestamp; neither is valid time."
            " Months observed run 1973-07 through 2026-05, 635 of them."
        ),
        "evidence_url": OCD_FTP_PAGE_URL,
    }


def _declaration(
    rule_id: str,
    *,
    source_id: str,
    stage: str,
    fields: list[str],
    spec: dict[str, object],
    rule: str,
    rationale: str,
    evidence_url: str = OCD_FTP_PAGE_URL,
) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "source_id": source_id,
        "stage": stage,
        "rule_kind": "parse_directive",
        "applies_to_fields": ["all"],
        "spec": {**spec, "declares_fields": fields, "asserts_header": False},
        "rule": rule,
        "rationale": rationale,
        "evidence_url": evidence_url,
        "effective_from": PROMOTION_FROM,
    }


NM_PROMOTION_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "cr_nm_wcproduction_api10_1",
        "source_id": "nm_ocd_wcproduction",
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
        },
        "rule": (
            "The NM API-10 is state code 30, the county code padded to three and the well"
            " number padded to five, concatenated as SSCCCUUUUU."
        ),
        "rationale": (
            "NM ships the three segments unpadded, and each pads to its own width: over"
            " 48,104,334 records api_cnty_cde is one or two characters and api_well_idn one to"
            " six, with exactly one record reaching six."
            " Concatenating them first and padding the result is a different and wrong key -"
            " '30' + '5' + '20178' padded to ten is 0030520178, not 3000520178 - so the widths"
            " are declared per column. 30 is the API state code for New Mexico and not its FIPS"
            " code (35), which is why the prefix is a rule rather than a slice of a field that"
            " looks like it already carries one. The one over-wide record, 30-15-256350 at"
            " ordinal 15,226,075, is refused as key_incomplete rather than padded: zfill does"
            " not truncate and would emit an eleven-character API-10, while SQL's lpad(5)"
            " truncates it to 25635, a real well with 487 rows of its own, and would file this"
            " row's volume under another well's identity. Both were measured. charset is the"
            " other half of the same guarantee, because a run of letters satisfies a width as"
            " well as a run of digits does;"
            " min_width is declared only on the state segment, which is '30' on every one"
            " of the 48.1M rows; the other two are genuinely short, so padding them is width"
            " normalisation rather than invention."
        ),
        "evidence_url": OCD_FTP_PAGE_URL,
    },
    {
        "rule_id": "cr_nm_wcproduction_entity_key_1",
        "source_id": "nm_ocd_wcproduction",
        "stage": "conform",
        "rule_kind": "key_composite",
        "applies_to_fields": ["api10", "pool_idn"],
        "spec": {
            "source_cols": ["api10", "pool_idn"],
            "separator": ":",
            "target_col": "entity_key",
            "entity_type": "well_completion_pool",
            "reporting_level": "well_completion_pool",
            "granularity": "well_observed",
            "requires_rule_id": "cr_nm_wcproduction_api10_1",
            "on_missing": "quarantine",
            "reason_code": "key_incomplete",
        },
        "rule": (
            "NM's entity is the well completion in a pool: the API-10 joined to the pool"
            " identifier the operator filed under."
        ),
        "rationale": (
            "The source carries no completion suffix - the identity is api_st_cde, api_cnty_cde"
            " and api_well_idn times pool_idn, and nothing else - so SB-01 §6.3's API-14 example"
            " is superseded by the bytes. The grain is not decorative: 48.1M rows hold 106,717"
            " distinct well x pool entities against 89,136 distinct wells, so a key of the"
            " API-10 alone would collapse 17,581 of them and the collided volumes would be"
            " quarantined as duplicates or, worse, silently promoted as one series."
            " reporting_level and entity_type are both well_completion_pool and granularity is"
            " well_observed, which is what migration 020's composition CHECK admits for that"
            " level. api10 is built by cr_nm_wcproduction_api10_1, which registry order puts"
            " first because rules execute by rule_id. pool_idn carries no charset bound: only"
            " its width was measured (5), and a class the corpus was never checked against"
            " would be an assertion rather than a measurement - the identity guarantee sits on"
            " the API segments, which were checked."
        ),
        "evidence_url": OCD_FTP_PAGE_URL,
    },
    {
        "rule_id": "cr_nm_wcproduction_county_parity_1",
        "source_id": "nm_ocd_wcproduction",
        "stage": "validate",
        "rule_kind": "validity_filter",
        "applies_to_fields": ["api_st_cde", "api_cnty_cde"],
        "spec": {
            "predicate_ast": {
                "and": [
                    {"cmp": [{"col": "api_st_cde"}, "==", {"lit": "30"}]},
                    {"not": {"is_null": {"col": "api_cnty_cde"}}},
                    {"cmp": [{"col": "api_cnty_cde"}, "!=", {"lit": ""}]},
                ]
            },
            "on_fail": "quarantine",
            "reason_code": "parse_error",
            "parity_filtering": "prohibited",
            "county_shape_rule_id": "cr_nm_wcproduction_api10_1",
            "evidence_grade": "LIKELY",
        },
        "rule": (
            "A New Mexico API begins with state code 30 and carries a county segment. County"
            " codes are never filtered on parity."
        ),
        "rationale": (
            "This rule is a prohibition, not a list of admissible counties. The evidence that"
            " NM county codes are odd is LIKELY and not VERIFIED (reconciliation.md:591, E9):"
            " Cibola is 30-006 and Los Alamos 30-028, and wellhistory carries 31 distinct county"
            " codes of which exactly one - 6, on 23 wells - is even. A parity predicate would"
            " therefore look correct against the production spine, where no even-coded county"
            " currently produces, and would delete Cibola in silence the month one did. A shape"
            " assertion is correct under either truth, so this rule asserts what can be checked"
            " here - the state segment is 30 and the county segment is present - and leaves the"
            " digits-and-width bound to cr_nm_wcproduction_api10_1's charset and pad, because"
            " the predicate AST is an allowlist of comparisons with no regular expression in it"
            " and restating the bound in a second place is how two rules drift. The reason code"
            " is parse_error, following nd_mpr.py:53's precedent for an identity that cannot be"
            " read, and the row is quarantined with it rather than dropped."
        ),
        "evidence_url": OCD_FTP_PAGE_URL,
    },
    {
        "rule_id": "cr_nm_wcproduction_stream_vocab_1",
        "source_id": "nm_ocd_wcproduction",
        "stage": "conform",
        "rule_kind": "vocab_map",
        "applies_to_fields": ["stream_raw"],
        "spec": {
            "mapping_table": "nm_stream_promoted_map",
            "key_col": "stream_raw",
            "value_col": "stream_canonical",
            "source_field": "prd_knd_cde",
            "trim_rule_id": "cr_nm_wcproduction_pad_1",
            "unmapped_action": "quarantine",
            "reason_code": "stream_not_promoted",
        },
        "rule": (
            "Map the trimmed prd_knd_cde to the canonical stream; a code the map does not carry"
            " is quarantined rather than guessed."
        ),
        "rationale": (
            "Four codes exist and all four are seeded: over 48,104,334 records, 'G ' 21,365,001,"
            " 'O ' 13,708,465, 'W ' 13,027,470 and 'C ' 3,398. The map is keyed on the trimmed"
            " value because prd_knd_cde is CHAR(2) and staging keeps what the source shipped;"
            " the trim is cr_nm_wcproduction_pad_1's declared mapping decision, and an exact"
            " match against the padded value would quarantine 100 percent of the spine as"
            " stream_not_promoted while every rule reported success. 'C ' is condensate and"
            " every one of its rows falls in 1986-1993, with none inside the 2015-01 promotion"
            " window: a vocabulary measured on the window would have quarantined all 3,398 on"
            " the day the window widened, which is why the seed carries the code the first"
            " promotion will never see. canonical.production_monthly has admitted condensate"
            " since migration 021. The reading of 'C' as condensate is the petroleum-convention"
            " one and the OCD publishes no codebook for prd_knd_cde, so it is stated here where"
            " a reader can check it rather than left implicit: the alternative is not caution"
            " but holding back 3,398 volumes the regulator did file, under a code that is"
            " undocumented rather than unknown."
        ),
        "evidence_url": OCD_FTP_PAGE_URL,
    },
    {
        "rule_id": "cr_nm_wcproduction_units_1",
        "source_id": "nm_ocd_wcproduction",
        "stage": "conform",
        "rule_kind": "unit_conform",
        "applies_to_fields": ["prod_amt"],
        "spec": {
            "units_by_stream": {
                "oil": "bbl",
                "condensate": "bbl",
                "gas": "mcf",
                "water": "bbl",
            },
            "volume_field": "prod_amt",
            "factor": "1",
            "rounding": "half_even",
            "scale": 3,
            "conditions_note": (
                "mcf at the regulator's stated conditions; conditions recorded, not normalised"
            ),
        },
        "rule": (
            "NM files one amount column whose unit the stream decides: bbl for oil, condensate"
            " and water, mcf for gas. No conversion, declared units."
        ),
        "rationale": (
            "Blueprint §3.0.3's gas-conditions rule and the A-13 unit-declaration obligation."
            " The declaration is keyed by stream rather than by column because NM ships a single"
            " prod_amt discriminated by prd_knd_cde, where ND ships three named columns - the"
            " same obligation, a different shape. The factor is 1 because the reported units"
            " already are the canonical ones; the rule exists to record that, and to pin the"
            " rounding mode and scale rather than inherit whatever the runtime defaults to. The"
            " gas-conditions statement is folded in here as a note because a standalone"
            " unit_conform carrying only conditions has no factor, rounding or scale and would"
            " raise RuleSpecError at conformance.py:82-86; ND folds it the same way. prod_amt is"
            " staged as text and cast before this rule runs: it is never null and never blank"
            " across 48.1M rows, and 6,812,255 of them report zero."
        ),
        "evidence_url": OCD_FTP_PAGE_URL,
    },
    _declaration(
        "cr_nm_wcproduction_liquids_1",
        source_id="nm_ocd_wcproduction",
        stage="conform",
        fields=["prd_knd_cde", "prod_amt"],
        spec={
            "liquids_policy": "oil_and_condensate_reported_separately",
            "oil_includes_condensate": False,
            "condensate_stream": "condensate",
            "condensate_months_observed": "1986-01 through 1993-12",
        },
        rule=(
            "NM reports condensate as its own stream, so an NM oil figure is oil as filed and"
            " any liquids figure that adds condensate to it says so."
        ),
        rationale=(
            "T1-b asked whether NM has a condensate discriminator and assumed the answer was no,"
            " in which case NM would have carried stream = oil with"
            " liquids_policy = oil_plus_condensate, as ND does. The artifact answers otherwise:"
            " prd_knd_cde carries 'C ' on 3,398 rows, so for those months oil and condensate are"
            " two filings and adding them silently would restate the operator. Liquid without"
            " qualification means oil plus condensate in this product, which is exactly why the"
            " policy travels with the figure: an NM liquids rollup is the labelled sum of the"
            " oil and condensate streams, never an oil row quietly containing both. Where the"
            " operator filed no condensate row - every month after 1993 - the oil row is what"
            " was filed and nothing is added to it."
        ),
    ),
    _declaration(
        "cr_nm_wcproduction_null_semantics_1",
        source_id="nm_ocd_wcproduction",
        stage="conform",
        fields=["prod_amt"],
        spec={
            "canonical_column": "null_semantics",
            "vocabulary": ["reported", "reported_zero", "no_report", "withheld"],
            "collapse": "never",
            "measured": {"null_prod_amt": 0, "reported_zero": 6812255},
        },
        rule=(
            "Why a volume is absent is a fact with its own vocabulary; a reported zero is not an"
            " absence, and neither is ever collapsed into the other."
        ),
        rationale=(
            "prod_amt is never null and never blank across 48,104,334 records and 6,812,255 rows"
            " report zero, so NM's live distinction is reported against reported_zero and the"
            " absent states are defensive rather than observed. The vocabulary written here is"
            " the one migration 009's CHECK admits - reported, reported_zero, no_report,"
            " withheld. PLAN-NM P3.3 named withheld_confidential and not_applicable, which that"
            " CHECK rejects; D1 writes what the constraint admits and does not alter another"
            " track's constraint to fit its own rule (entry gate G6). A filter would delete the"
            " row that carries the absence, which is the distinction this rule exists to keep"
            " (§3.0.3)."
        ),
    ),
    _declaration(
        "cr_nm_wcproduction_amend_ind_1",
        source_id="nm_ocd_wcproduction",
        stage="conform",
        fields=["amend_ind"],
        spec={
            "domain": ["N", "Y", "1", "2", "3", "4", "6", "7", "9", "X"],
            "counts": {
                "N": 34812326, "Y": 13280514, "1": 5959, "2": 5252, "4": 185,
                "6": 72, "9": 10, "3": 8, "X": 6, "7": 2,
            },
            "boolean_reading": "prohibited",
            "promoted": False,
            "change_detection_rule_id": "cr_nm_wcproduction_mod_dte_1",
        },
        rule=(
            "amend_ind is a ten-value vocabulary carried verbatim into staging, promoted to no"
            " canonical column, and never read as a Y/N flag."
        ),
        rationale=(
            "Measured identically on the XML side and off the staged Parquet: N 34,812,326,"
            " Y 13,280,514, then 1, 2, 4, 6, 9, 3, X and 7 across 11,494 rows. A boolean reading"
            " mis-classifies every one of those 11,494, and it is the reading a column named"
            " _ind invites. The eight numeric and X codes are undocumented - the OCD publishes"
            " no codebook for them - so nothing is promoted from this column and the raw value"
            " stays staged where a later phase holding a codebook can map it under a new rule"
            " row. Its part in change detection belongs to cr_nm_wcproduction_mod_dte_1:"
            " amend_ind is the regulator's evidence that a row was amended, not the trigger,"
            " because the trigger is a value change."
        ),
    ),
    _declaration(
        "cr_nm_wcproduction_status_vocab_1",
        source_id="nm_ocd_wcproduction",
        stage="conform",
        fields=["c115_wc_stat_cde"],
        spec={
            "domain": ["P", "F", "S", "T", "G", "I", "A", " ", "D", "p", "L"],
            "counts": {
                "P": 23532167, "F": 20557177, "S": 2686669, "T": 734301, "G": 391371,
                "I": 97456, "A": 47439, " ": 42366, "D": 15375, "p": 7, "L": 6,
            },
            "promoted": False,
            "target_map": "nm_status_map",
        },
        rule=(
            "The C-115 well-completion status code is staged verbatim and promoted to no"
            " canonical status until its codebook is in evidence."
        ),
        rationale=(
            "Eleven values were measured over all 48.1M records, and two of them are traps: a"
            " lowercase p on 7 rows and a single space on 42,366. An exact-match vocabulary"
            " seeded from a hand-copied distinct-value list that lost either would quarantine"
            " 42,373 rows as unknown_status, which is why the domain is recorded here with its"
            " counts. What the letters mean is a different question, and the OCD publishes no"
            " codebook mapping them to a well status: lineage.nm_status_map is therefore left"
            " empty rather than filled with a plausible guess, because a canonical status"
            " invented for an undocumented single-letter code is a mapping that exists only in"
            " the head of whoever guessed it, which is what R8 exists to prevent. When the"
            " codebook is in evidence the map is populated and a vocab_map row supersedes this"
            " declaration."
        ),
    ),
    _declaration(
        "cr_nm_wcproduction_restatement_1",
        source_id="nm_ocd_wcproduction",
        stage="conform",
        fields=["prod_amt", "amend_ind", "mod_dte"],
        spec={
            "on_change": "append_new_report_vintage",
            "in_place_update": "prohibited",
            "detection": (
                "value_hash change for the same entity_key, production_month and stream across"
                " report vintages"
            ),
            "amend_ind_role": "evidence",
            "mod_dte_role": "promotion_shortcut",
            "vintage_rule_id": "cr_nm_wcproduction_undated_vintage_1",
        },
        rule=(
            "A restated NM month is appended under a new report vintage. Nothing in canonical is"
            " ever updated in place."
        ),
        rationale=(
            "DIR-2 makes the vintage a dimension rather than an overwrite, and migration 008's"
            " append-only trigger (008:29-31) makes a canonical UPDATE an error rather than a"
            " warning, so this rule states what the trigger enforces and what the promotion must"
            " therefore do. The trigger for an append is a value change and not the regulator's"
            " flag: the export re-publishes all 48.1M rows nightly, 34,812,326 of them carrying"
            " amend_ind N, so reading the flag as the signal would treat a re-publication as a"
            " statement that nothing changed. amend_ind is kept as evidence beside the appended"
            " row, and mod_dte is a promotion shortcut compared against the staged prior"
            " partition; neither enters value_hash (cr_nm_wcproduction_mod_dte_1). The vintage"
            " itself is glasswell's own stamp because the artifact is undated and overwritten in"
            " place upstream (cr_nm_wcproduction_undated_vintage_1)."
        ),
    ),
    _declaration(
        "cr_nm_wcproduction_flare_property_1",
        source_id="nm_ocd_wcproduction",
        stage="conform",
        fields=[],
        spec={
            "flare_reporting_grain": "property",
            "well_completion_flare_series": "not_derivable",
            "sources_out_of_scope": ["othervolume", "podvolume", "podstorage", "wcinjection"],
            "served": False,
        },
        rule=(
            "NM flaring is filed against a Property, not a well completion, so no NM flare"
            " volume is derived at the spine's grain and none is served."
        ),
        rationale=(
            "The disposition artifacts that carry it - othervolume, podvolume, podstorage and"
            " wcinjection, 738 MB combined - are deliberately not fetched, because the volume"
            " they hold attaches to a Property while this spine's grain is well completion x"
            " pool. Splitting a Property's flare volume across its completions would put an"
            " estimate into canonical, and DIR-3 keeps canonical at native granularity with"
            " estimates named as such elsewhere. The decision is a row rather than a note so"
            " that a reader asking for NM flaring finds the reason, and so that a later phase"
            " which does fetch the disposition tables supersedes a stated decision instead of"
            " discovering an unstated one."
        ),
        evidence_url=OCD_DATA_URL,
    ),
    _declaration(
        "cr_nm_pool_vocab_1",
        source_id="nm_ocd_pool",
        stage="conform",
        fields=["pool_idn", "pool_nam"],
        spec={
            "identity": "pool_idn",
            "label": "pool_nam",
            "label_trim_rule_id": "cr_nm_pool_pad_1",
            "target_map": "nm_pool_map",
            "populated_by": "dimension_promotion",
            "unknown_pool": "orphan_fk",
        },
        rule=(
            "pool_idn is the pool's identity and pool_nam only its label; the label is resolved"
            " from the staged registry, never from a literal."
        ),
        rationale=(
            "The registry holds 5,084 pools and the spine 106,717 well x pool entities, so the"
            " entity key carries the identifier: a name is the regulator's prose, arrives"
            " CHAR(35)-padded, and is trimmed under cr_nm_pool_pad_1 before anyone reads it."
            " lineage.nm_pool_map is populated from the staged registry when the dimension is"
            " promoted rather than seeded from the test fixture, because that fixture holds 300"
            " of the 5,084 pools and a vocabulary seeded from it would quarantine the other"
            " 94 percent. A pool_idn the registry does not carry is an orphan_fk quarantine,"
            " counted and kept, never dropped."
        ),
    ),
    _declaration(
        "cr_nm_wchistory_status_vocab_1",
        source_id="nm_ocd_wchistory",
        stage="conform",
        fields=["wc_stat_cde"],
        spec={
            "promoted": False,
            "domain_measured": False,
            "measured_by": "dimension_promotion",
            "target_map": "nm_status_map",
        },
        rule=(
            "The well-completion status code is staged verbatim; this slice asserts no canonical"
            " status for it."
        ),
        rationale=(
            "Phase 2 measured this source's column widths but not this column's domain over its"
            " 426,529 rows, and the 300-record fixture cannot establish a vocabulary: the"
            " spine's own c115_wc_stat_cde is the cautionary case, where a lowercase p on 7 rows"
            " and a single space on 42,366 would both have been missed by a sample. The"
            " dimension promotion reads this source in full, so it measures the domain there and"
            " seeds the mapping as a superseding row with that measurement as its evidence."
            " Until then the code is staged and unmapped, which is a state this registry can"
            " express and a partial vocabulary is not."
        ),
    ),
    _declaration(
        "cr_nm_wcproduction_window_1",
        source_id="nm_ocd_wcproduction",
        stage="conform",
        fields=["prodn_yr", "prodn_mth"],
        spec={
            "promotion_window_start": PROMOTION_WINDOW_START.isoformat(),
            "promotion_window_end": None,
            "re_runnable": True,
            "widening": "a re-run under a later vintage, recorded in lineage.vintages",
        },
        rule=(
            "The spine promotes production months from 2015-01 onward. The window is a"
            " promotion parameter, not a property of the artifact: staging holds all 635"
            " months and widening it is a re-run."
        ),
        rationale=(
            "DIR-12's ruling. The staged corpus runs 1973-07 to 2026-07 and the deliverables"
            " D1 exists for - the allocation validator's substrate and a modern Permian spine -"
            " need 2015 onward, where 17,645,580 of the 48,104,334 staged rows and 80,624 of the"
            " 106,717 well x pool entities live. The measurement that would have decided it"
            " otherwise was taken: a month is 126,947 rows on average and never more than"
            " 147,714, so full history is 635 batches rather than a different design, and the"
            " bounded window costs nothing structural. What it does cost is stated rather than"
            " hidden: D3's validator sees a shallower vintage spread and SB-01 §8.2's"
            " wells-per-lease distribution is measured over eleven years instead of fifty-three."
            " The effective window is stamped on every promotion derivation, so a figure served"
            " from a widened run is distinguishable from one served before it."
        ),
    ),
    _declaration(
        "cr_nm_wcproduction_days_1",
        source_id="nm_ocd_wcproduction",
        stage="conform",
        fields=["prodn_day_num"],
        spec={
            "source_field": "prodn_day_num",
            "canonical_column": "days_produced",
            "minimum": 0,
            "maximum": "days_in_production_month",
            "on_out_of_domain": "withhold",
            "withhold_scope": "days_produced",
            "measured": {
                "rows_past_the_month_length": 244025,
                "rows_past_the_month_length_in_window": 41593,
                "value_99": 131531,
                "observed_range": [0, 99],
            },
        },
        rule=(
            "prodn_day_num promotes as days_produced only when it is between zero and the"
            " length of the month it is filed for. Anything else is withheld, and the volume"
            " beside it still promotes."
        ),
        rationale=(
            "Measured over all 48,104,334 rows: prodn_day_num runs 0 to 99, and 244,025 rows"
            " (41,593 inside the window) carry a count longer than the month they are filed"
            " for - mostly 31 in a thirty-day month, but also 32, 40, 66 and 99. 99 alone is on"
            " 131,531 rows and reads like a sentinel, which is a LIKELY reading and not a"
            " documented one, so nothing is inferred from it. A day count longer than its own"
            " month is not a day count, and serving one as a figure would be a naked number with"
            " a derivation handle attached to it. It is withheld rather than corrected, and the"
            " raw value stays in staging where a later rule with a codebook can map it. The"
            " volume is a separate measurement and is unaffected: withholding it too would"
            " delete 41,593 real filings over a defect in a different column."
        ),
    ),
    _declaration(
        "cr_nm_wcproduction_collision_1",
        source_id="nm_ocd_wcproduction",
        stage="conform",
        fields=["ogrid_cde", "amend_ind", "prod_amt", "prodn_day_num"],
        spec={
            "grain": ["entity_key", "production_month", "stream"],
            "agreeing_rows": "promote the lowest source_row_ordinal, quarantine the rest",
            "agreeing_reason_code": "duplicate_row",
            "disagreeing_rows": "promote nothing, quarantine every row",
            "disagreeing_reason_code": "key_collision",
            "summing": "prohibited",
            "amend_ind_tiebreak": "prohibited",
            "measured": {
                "groups_in_window": 25029,
                "group_size": 2,
                "groups_with_two_ogrids": 24838,
                "agreeing_groups": 2438,
                "disagreeing_groups": 22591,
                "amount_disagreeing_groups": 19465,
                "amount_disagreeing_with_both_producing": 12351,
                "amount_disagreeing_separated_by_amend_ind": 5106,
                "day_totals_past_the_month_length": 5059,
            },
        },
        rule=(
            "Where the artifact files two rows for one well completion, pool, month and stream,"
            " an identical measurement promotes once and a differing one promotes not at all."
        ),
        rationale=(
            "25,029 in-window well-completion-months carry two rows, every group is exactly two,"
            " and 24,838 of them carry two different OGRIDs - an operator change filed by both"
            " operators. Summing them is refuted by the artifact rather than disliked: 5,059"
            " pairs already report more producing days between them than the month has, so they"
            " are not two halves of one month, and 5,564 pairs report the identical amount"
            " twice, which summing would double. Choosing between them is refuted the same way:"
            " of the 19,465 pairs that disagree on the amount, 12,351 have both rows producing"
            " and 801 differ more than tenfold, while amend_ind separates only 5,106 of them,"
            " and picking the first by file order is how a served figure becomes a coin toss"
            " (fp-audit D1). So the S-E row is withheld and both filings are quarantined as"
            " key_collision, where the count is visible and the rows are recoverable; 45,182"
            " in-window rows sit there, 0.26 percent of the window. Where both rows say the same"
            " thing there is nothing to choose between, so one promotes and the second is a"
            " duplicate_row. The resolution this defers - which operator's filing is the month -"
            " needs operator effectivity from wchistory or podwc and is a rule row a later phase"
            " writes, not an inference this one makes."
        ),
    ),
    {
        "rule_id": "cr_nm_wcproduction_volume_range_1",
        "source_id": "nm_ocd_wcproduction",
        "stage": "validate",
        "rule_kind": "validity_filter",
        "applies_to_fields": ["prod_amt"],
        "spec": {
            "predicate_ast": {"cmp": [{"col": "prod_amt"}, ">=", {"lit": 0}]},
            "on_fail": "quarantine",
            "reason_code": "impossible_volume",
            "measured": {"negative_rows": 3, "negative_rows_in_window": 0},
        },
        "rule": "A produced volume is never negative; a row that reports one is quarantined.",
        "rationale": (
            "Three rows in 48,104,334 report a negative amount: -39 mcf of gas in 1993-12 and"
            " -104 and -97 barrels of oil in 1993-05, all three carrying amend_ind Y, which"
            " reads like an amendment filed as a correction against a prior month rather than a"
            " measurement. Whatever it is, it is not a volume produced, and canonical carries"
            " observations. None of the three is inside the 2015-01 window, and that is exactly"
            " why the rule is seeded now: a validity rule measured on the window would admit"
            " them silently on the day the window widens, which is the trap"
            " cr_nm_wcproduction_stream_vocab_1's fourth code already had to avoid. The bound is"
            " zero rather than a positive floor because a reported zero is a real filing that"
            " 6,812,255 rows make (cr_nm_wcproduction_null_semantics_1)."
        ),
        "evidence_url": OCD_FTP_PAGE_URL,
        "effective_from": PROMOTION_FROM,
    },
    {
        "rule_id": "cr_nm_ogrid_operator_1",
        "source_id": "nm_ocd_ogrid",
        "stage": "join",
        "rule_kind": "alias_join",
        "applies_to_fields": ["operator_raw"],
        "spec": {
            "alias_table": "operator_aliases",
            "key_cols": ["operator_raw"],
            "target_col": "operator",
            "min_confidence": "1.0",
            "method": "exact_key",
            "source_field": "ogrid_cde",
            "unmatched_action": "quarantine",
            "reason_code": "alias_unresolved",
        },
        "rule": "OGRID is an exact operator key: it joins at confidence 1.0 or it does not join.",
        "rationale": (
            "OGRID is the OCD's own registered operator identifier and the ogrid registry, 31,696"
            " rows of it, is its authority - so this is a key lookup, not a name match, and it"
            " carries confidence 1.0 by construction rather than by scoring. ND's operator"
            " arrives as free text and its alias table records fuzzy confidences; NM's does not"
            " need to. SB-01 §5.3 is the reason the difference matters: a fuzzy operator match is"
            " an unlabelled estimate in the identity layer, which is the one place this system"
            " cannot afford one. An OGRID with no registry row is alias_unresolved, counted,"
            " never dropped. The frame's ogrid_cde is renamed to operator_raw before the join"
            " because the executor keys the alias table by the frame's own column name"
            " (conformance.py:158), and lineage.operator_aliases is read whole with no source"
            " filter - so the registry must be loaded with OGRID codes that cannot collide with"
            " another jurisdiction's operator keys, or the executor refuses the duplicate."
        ),
        "evidence_url": OCD_FTP_DESCRIPTIONS_URL,
        "effective_from": PROMOTION_FROM,
    },
)

# Phase 5's rows: the completion dimension D3's Validator B is built on. They are a separate
# tuple from NM_PROMOTION_RULES because that tuple is the spine's, and tests/integration/
# test_nm_seed_rules.py parametrises over it to prove every spine rule meets a probe frame.
NM_DIMENSION_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "cr_nm_wchistory_api10_1",
        "source_id": "nm_ocd_wchistory",
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
        },
        "rule": (
            "wchistory's API-10 is built exactly as wcproduction's: state code 30, county padded"
            " to three, well number padded to five."
        ),
        "rationale": (
            "The dimension has to key identically to the spine or the two never join, so this row"
            " restates cr_nm_wcproduction_api10_1's widths against wchistory's own measurements"
            " rather than pointing at another source's rule - load_rules reads one source_id per"
            " call, so a rule row cannot be shared across sources. The widths were re-measured on"
            " this source: over 426,529 records api_well_idn is 1 char on 22, 2 on 414, 3 on"
            " 6,574, 4 on 69,322 and 5 on 350,197, and nothing reaches six, so wchistory has no"
            " counterpart to the one over-wide wcproduction record. The pads, the charset bound"
            " and the key_incomplete exit are the same because the failure modes are the same:"
            " zfill overbuilds and lpad truncates onto a different real well."
        ),
        "evidence_url": OCD_FTP_PAGE_URL,
        "effective_from": PROMOTION_FROM,
    },
    {
        "rule_id": "cr_nm_wchistory_completion_key_1",
        "source_id": "nm_ocd_wchistory",
        "stage": "conform",
        "rule_kind": "key_composite",
        "applies_to_fields": ["api10", "pool_idn"],
        "spec": {
            "source_cols": ["api10", "pool_idn"],
            "separator": ":",
            "target_col": "completion_key",
            "entity_type": "well_completion_pool",
            "reporting_level": "well_completion_pool",
            "requires_rule_id": "cr_nm_wchistory_api10_1",
            "on_missing": "quarantine",
            "reason_code": "key_incomplete",
        },
        "rule": (
            "A completion is the API-10 joined to its pool, and that string is the same"
            " completion_key the production rows carry as entity_key."
        ),
        "rationale": (
            "canonical.well_completions.completion_key is documented (migration 022) as the S-E"
            " entity_key of the production rows that report the completion, so the dimension's"
            " key is built by the same composition cr_nm_wcproduction_entity_key_1 declares:"
            " api10 + ':' + pool_idn. wchistory holds 147,975 distinct completions over 121,940"
            " distinct wells, so keying the dimension on the API-10 alone would collapse 26,035"
            " of them onto a neighbour's identifiers. Registry order matters and is load-bearing:"
            " rules execute by rule_id, and cr_nm_wchistory_api10_1 sorts before this row, which"
            " needs the column it builds."
        ),
        "evidence_url": OCD_FTP_PAGE_URL,
        "effective_from": PROMOTION_FROM,
    },
    _declaration(
        "cr_nm_wchistory_effective_1",
        source_id="nm_ocd_wchistory",
        stage="conform",
        fields=["eff_dte", "rec_termn_dte"],
        spec={
            "effective_from_field": "eff_dte",
            "termination_field": "rec_termn_dte",
            "open_sentinel": "9999-12-31",
            "on_change": "append_new_row",
            "in_place_update": "prohibited",
            "measured": {
                "rows": 426529,
                "completions": 147975,
                "open_rows": 147975,
                "duplicate_completion_effective_dates": 0,
                "eff_dte_range": ["1900-01-01", "2026-08-19"],
            },
        },
        rule=(
            "eff_dte is the completion observation's effective_from and rec_termn_dte 9999-12-31"
            " marks the open record. A change is a new row, never an update."
        ),
        rationale=(
            "canonical.wells is append-only and effective-dated for this reason (migration 009:"
            " a status change is a new row, never an update), and wchistory is already shaped"
            " that way - it is NM's own history table. Measured over all 426,529 records:"
            " (completion, eff_dte) is unique, 0 duplicate groups, so the effective grain needs"
            " no collision routing of its own; and exactly one record per completion carries"
            " rec_termn_dte 9999-12-31, 147,975 open rows against 147,975 completions, so the"
            " sentinel is the regulator's own open-record marker rather than an inference."
            " Every observation is promoted, not only the open one: a dimension that keeps only"
            " the current row cannot answer an as-of question, and DIR-2 makes as-of the point."
            " eff_dte reaches back to 1900-01-01, which is a filing convention rather than a"
            " date, and it is carried verbatim because narrowing it here would be an opinion"
            " staging is not allowed to hold."
        ),
    ),
    _declaration(
        "cr_nm_wchistory_wellbore_policy_1",
        source_id="nm_ocd_wchistory",
        stage="conform",
        fields=["api_st_cde", "api_cnty_cde", "api_well_idn", "well_nbr_idn"],
        spec={
            "policy": "one_producing_wellbore_per_api10",
            "detection_source": "wchistory",
            "detection_field": None,
            "status": "vacuous",
            "reason_code": "multi_wellbore_policy",
            "measured": {
                "api_suffix_columns_in_scope": 0,
                "well_nbr_idn_distinct": 4854,
                "well_nbr_idn_rows": 426529,
                "well_nbr_idn_top": ["001", "002", "003", "004", "001H"],
            },
        },
        rule=(
            "NM cannot express a sidetrack, so the one-producing-wellbore-per-API-10 policy is"
            " vacuously satisfied and no wellbore is quarantined under it."
        ),
        rationale=(
            "SB-01 §5.3 assumes one producing wellbore per API-10 and detects the exception on"
            " the API-12 suffix, naming wchistory as NM's detection source. wchistory has no such"
            " column. The T1-d element inventory, measured over every record of all nine in-scope"
            " artifacts, holds api_st_cde, api_cnty_cde and api_well_idn and nothing past them;"
            " the probe found no completion suffix in wcproduction and this row records that"
            " wchistory has none either. well_nbr_idn is the operator's well number, not a"
            " wellbore suffix: 4,854 distinct values over 426,529 records and 121,940 wells, with"
            " '001' on 72,977 rows, so it repeats across wells rather than distinguishing bores"
            " within one. The policy is therefore vacuous, and this row says vacuous rather than"
            " reporting a 0% share: a metric that cannot be non-zero is not a measurement, and"
            " serving 0% would read as evidence that NM has no sidetracks when what is true is"
            " that the artifact cannot say. If NM ever ships a suffix, the successor row is where"
            " the share becomes measurable."
        ),
        evidence_url=OCD_FTP_DESCRIPTIONS_URL,
    ),
    _declaration(
        "cr_nm_wchistory_status_domain_1",
        source_id="nm_ocd_wchistory",
        stage="conform",
        fields=["wc_stat_cde"],
        spec={
            "promoted_to": "status_reported",
            "status_canonical": None,
            "mapping_table": None,
            "measured_domain": {
                "A": 270845, "N": 62724, "P": 51724, "T": 16084, "C": 14152,
                "S": 4695, " ": 4380, "Z": 1624, "D": 212, "X": 89,
            },
            "measured_rows": 426529,
            "complements_rule_id": "cr_nm_wchistory_status_vocab_1",
        },
        rule=(
            "wc_stat_cde has ten values and they are promoted verbatim as status_reported."
            " status_canonical stays null because no codebook maps them."
        ),
        rationale=(
            "cr_nm_wchistory_status_vocab_1 recorded that the domain of this column was never"
            " measured; P5 reads the source in full, so it is measured here: A 270,845, N 62,724,"
            " P 51,724, T 16,084, C 14,152, S 4,695, a single space 4,380, Z 1,624, D 212 and X"
            " 89, over all 426,529 records. The blank is real data and is carried, exactly as"
            " c115_wc_stat_cde's blank is on the spine. Measuring the domain does not produce a"
            " mapping: NM publishes no codebook for these letters, and guessing that A is active"
            " would put an unlabelled estimate in the status column, which is the R8 violation"
            " this registry exists to prevent. So status_reported carries the letter and"
            " status_canonical is null - an absent mapping, not a mapping to null."
            " lineage.nm_status_map stays empty for the same reason, and this row is what a"
            " reader auditing that empty relation should find."
        ),
        evidence_url=OCD_FTP_DESCRIPTIONS_URL,
    ),
    _declaration(
        "cr_nm_wchistory_lease_identifier_1",
        source_id="nm_ocd_wchistory",
        stage="conform",
        fields=["spc_unit_idn", "prod_prop_idn"],
        spec={
            "spacing_unit_field": "spc_unit_idn",
            "property_field": "prod_prop_idn",
            "absent_sentinels": ["0", ""],
            "on_no_identifier": "quarantine",
            "reason_code": "orphan_fk",
            "registry_resolution_is_not_required": True,
            "measured": {
                "spc_unit_idn_zero_rows": 119662,
                "prod_prop_idn_zero_rows": 7,
                "spc_unit_idn_not_in_spacingunit_registry": 21239,
                "prod_prop_idn_not_in_property_registry": 1,
            },
        },
        rule=(
            "spc_unit_idn and prod_prop_idn of '0' mean absent, not identifier zero. A completion"
            " that resolves no POD, no spacing unit and no property is quarantined as orphan_fk,"
            " counted, never dropped."
        ),
        rationale=(
            "119,662 of 426,529 records carry spc_unit_idn '0' and 7 carry prod_prop_idn '0'."
            " Promoting those verbatim would create a spacing unit named zero holding a quarter"
            " of New Mexico, and every Validator B group keyed on it would be an artefact of a"
            " sentinel. They land null instead, which is what absent means. The identifiers are"
            " promoted as filed even when the registry has no row for them - 21,239 distinct"
            " spacing-unit references and 1 property reference do not resolve - because the"
            " reference is the regulator's own and dropping it would lose grouping power the"
            " artifact does have; the unresolved counts are published here rather than hidden by"
            " a join. What is refused is a completion with none of the three: it cannot enter a"
            " lease-equivalent group at all, so it is quarantined with its payload and counted"
            " rather than promoted as a row no grouping key can reach."
        ),
    ),
    _declaration(
        "cr_nm_podwc_pod_1",
        source_id="nm_ocd_podwc",
        stage="join",
        fields=["pod_idn", "api_st_cde", "api_cnty_cde", "api_well_idn", "pool_idn", "eff_dte"],
        spec={
            "join_cols": ["api10", "pool_idn"],
            "effective_predicate": "podwc.eff_dte <= well_completions.effective_from",
            "on_multiple": "fan_out",
            "on_none": "null_pod_id",
            "measured": {
                # Both figures below are on the grain this rule's own predicate joins at:
                # eff_dte truncated to its date. podwc timestamps every row, so a
                # timestamp-grained measurement is a different grouping and a smaller one.
                "measured_at": "date",
                "podwc_rows": 224778,
                "podwc_completions": 93685,
                "pods_per_completion_at_one_eff_dte": {"2": 44061, "3": 35859, "4": 417,
                                                       "5": 274, "6": 51, "7": 1},
                "pods_per_completion_at_one_eff_timestamp": {"2": 34835, "3": 35857, "4": 417,
                                                             "5": 274, "6": 51, "7": 1},
                "pod_typ_cde": {"G": 58107, "O": 49108, "W": 36678, "M": 51, "C": 11},
                "fanned_out_rows": 763473,
                "fanned_out_rows_at_one_eff_timestamp": 762522,
                "podwc_pods_absent_from_pod_registry": 17,
            },
        },
        rule=(
            "A completion's PODs are the distinct pod_idn crosswalked to it whose eff_dte is on"
            " or before the observation's effective_from. More than one is more than one row."
        ),
        rationale=(
            "NM's POD is stream-scoped: the pod registry types 58,107 of them G, 49,108 O and"
            " 36,678 W, and 80,663 (completion, effective date) groups in podwc name two to"
            " seven distinct PODs on one date - measured at the date granularity this rule's own"
            " predicate joins at, because podwc timestamps every row and a timestamp-grained"
            " grouping splits those 80,663 into 71,435. A single-valued pod_id cannot be filled"
            " without choosing, and choosing between filings by file order is the defect the"
            " spine's collision rule already refuses. It fans out instead - a completion in three"
            " PODs is three dimension rows, the same shape P4 landed for a well producing from"
            " two pools - which loses nothing and keeps every crosswalk edge inside canonical,"
            " where staging's 30-day truncation cannot reach it. This is also why the analogue to"
            " a TX lease survives the fan-out rather than being weakened by it: SB-01 §6.2 keys"
            " canonical.leases on (oil_gas_code, district_no, lease_no), so a TX lease is"
            " stream-scoped in exactly the same way. podwc carries no termination date, so a POD"
            " once crosswalked is not withdrawn by the artifact and this rule does not invent a"
            " withdrawal; the effective predicate is one-sided for that reason. 17 pod_idn values"
            " have no row in the pod registry and are still carried, for the reason"
            " cr_nm_wchistory_lease_identifier_1 gives."
        ),
        evidence_url=OCD_FTP_DESCRIPTIONS_URL,
    ),
    _declaration(
        "cr_nm_ogrid_registry_1",
        source_id="nm_ocd_ogrid",
        stage="join",
        fields=["ogrid_cde", "ogrid_nam"],
        spec={
            "alias_table": "operator_aliases",
            "operator_raw_field": "ogrid_cde",
            "operator_field": "ogrid_nam",
            "method": "exact_key",
            "confidence": "1.000",
            "fuzzy_matching": "prohibited",
            "effective_from_field": "stat_eff_dte",
            "join_rule_id": "cr_nm_ogrid_operator_1",
            "measured": {
                "ogrid_rows": 31696,
                "duplicate_ogrid_codes": 0,
                "distinct_ogrid_in_wchistory": 2223,
                "wchistory_ogrids_absent_from_registry": 0,
            },
        },
        rule=(
            "lineage.operator_aliases is loaded from the ogrid registry: the code is the key, the"
            " registered name is the operator, confidence is 1.000 and the method is exact_key."
        ),
        rationale=(
            "SB-01 §5.3: a fuzzy operator match is an unlabelled estimate in the identity layer,"
            " which is the one place this system cannot afford one. OGRID is the OCD's own"
            " registered operator identifier, so the load is a key copy and the confidence is 1"
            " by construction rather than by scoring - there is no normalised-name pass and no"
            " threshold to tune. The registry holds 31,696 codes with 0 duplicates, which matters"
            " because lineage.operator_aliases is read whole with no source filter and"
            " _alias_join refuses duplicate keys above min_confidence. All 2,223 OGRID codes"
            " wchistory cites resolve, so alias_unresolved is empty on this corpus; the exit"
            " exists anyway because an unmatched code is counted and quarantined, never dropped,"
            " and a later artifact may cite a code the registry has not caught up with."
            " lineage.operator_aliases carries no method column, so exact_key is recorded here"
            " and in cr_nm_ogrid_operator_1's spec rather than on the alias row."
        ),
        evidence_url=OCD_FTP_DESCRIPTIONS_URL,
    ),
    _declaration(
        "cr_nm_wcproduction_lease_equivalent_1",
        source_id="nm_ocd_wcproduction",
        stage="join",
        fields=["source_operator_key", "pool_idn", "pod_id", "spacing_unit_id", "property_id"],
        spec={
            "consumer": "SB-01 §8.6 Validator B",
            "grouping_key": [
                "source_operator_key",
                "pool_idn",
                "pod_id | spacing_unit_id | property_id",
            ],
            "grouping_source": "canonical.well_completions",
            "geometry_available": False,
            "resampling": "post_hoc_group_selection_reweighting",
            "residual_mismatch": "must_be_published",
            "transferability": "lease_composition_covariates_only",
            "measured_wells_per_group": {
                "basis": (
                    "canonical.well_completions, the latest observation per completion:"
                    " 147,975 completions, 121,940 wells"
                ),
                # POD is counted on the fanned completion x POD grain, which is why it holds
                # more groups than the completions it reaches; the other two are counted once
                # per completion. One label cannot cover both grains honestly.
                "basis_pod": "the fanned completion x POD grain",
                "basis_spacing_unit_and_property": "one row per completion",
                "pod": {"groups": 141479, "well_slots": 204498, "mean": "1.445",
                        "p50": 1, "p90": 2, "max": 269, "singletons": 126676},
                "spacing_unit": {"groups": 49994, "well_slots": 81100, "mean": "1.622",
                                 "p50": 1, "p90": 3, "max": 62, "singletons": 34697},
                "property": {"groups": 52406, "well_slots": 147975, "mean": "2.824",
                             "p50": 1, "p90": 4, "max": 641, "singletons": 34114},
                "completions_reached": {"pod": 83814, "spacing_unit": 81100,
                                        "property": 147975, "total": 147975},
                # Every POD ever crosswalked, ignoring cr_nm_podwc_pod_1's effective predicate.
                # The gap is what the predicate withholds, and it is stated rather than tuned.
                "pod_ignoring_effective_predicate": {"groups": 151201, "well_slots": 224711},
                "tx_target_distribution": "unmeasured - canonical.leases has no producer yet",
            },
        },
        rule=(
            "Validator B groups NM synthetic lease-equivalents on (source_operator_key, pool_idn,"
            " pod_id | spacing_unit_id | property_id), read from canonical.well_completions."
        ),
        rationale=(
            "SB-01 §8.6 step 2 groups NM synthetic lease-equivalents on operator, pool and"
            " spatial contiguity within a stated distance in geom_compute. NM OCD's FTP ships no"
            " coordinates - confirmed in the bytes: latitude and longitude appear on wellhistory"
            " alone, blank on ~1,892 of its 321,510 rows, and on none of the eight other in-scope"
            " artifacts, so no coordinate reaches the completion grain at all. Validator B as"
            " written cannot be built from D1's data."
            " The substitute is better on one axis and worse on another, and both are recorded"
            " here. Better: a TX lease is a legal unit, not a distance, and NM publishes its own"
            " legal units - spacingunit, pod/podwc (NM's own aggregation unit, its closest"
            " analogue to a lease) and property (the unit NM reports flaring against). Grouping"
            " on (OGRID, pool, POD | spacing unit | property) is a closer analogue than proximity"
            " and needs no geometry."
            " Worse: it removes the resampling knob. SB-01 §8.6 step 2 resamples synthetic groups"
            " to match the TX joint distribution of wells-per-lease; legal units come in the"
            " sizes they come in and cannot be tuned continuously. The honest substitute is"
            " post-hoc group-selection reweighting - select and weight from the observed"
            " legal-unit population to approximate the TX distribution, and publish the residual"
            " mismatch rather than claiming a match."
            " The observed population is measured here, on the promoted rows rather than on"
            " staging, so the reweighting has something to reweight. Over the 147,975"
            " completions at their latest observation: (OGRID, pool, POD) gives 141,479 groups,"
            " mean 1.445 wells, median 1, p90 2, max 269, and 126,676 of them - 89.5% - hold a"
            " single well, and it reaches 83,814 completions; (OGRID, pool, spacing unit) gives"
            " 49,994 groups over 81,100 well-slots, mean 1.622, median 1, p90 3, max 62, and"
            " reaches 81,100 completions; (OGRID, pool, property) gives 52,406 groups, mean"
            " 2.824, median 1, p90 4, max 641, and reaches all 147,975. Property is the only key"
            " with full coverage, and every key's median group is one well - a group of one is"
            " not a lease-equivalent for an allocation validator, because it tests no"
            " allocation. That is the ceiling on what reweighting can reach and it is published"
            " rather than smoothed. The TX side of the residual cannot be computed in D1:"
            " canonical.leases has no producer yet, so the target distribution is unmeasured and"
            " D3 must publish the residual once D2 lands it."
            " The transferability caveat, from SB-01 §8.6: bounds established on synthetic"
            " lease-equivalents transfer on lease-composition covariates, not on rock. NM"
            " Delaware is not TX Midland. A bound calibrated here describes how much error"
            " aggregating wells into a legal unit can hide; it does not describe how a Midland"
            " well produces."
        ),
        evidence_url=OCD_FTP_DESCRIPTIONS_URL,
    ),
)

NM_RULES: tuple[dict[str, object], ...] = (
    *(
        family(table)
        for table, _ in NM_TABLES
        for family in (_undated_vintage, _ftp_layout, _host_pin, _parse, _pad)
    ),
    _mod_dte(),
    _month(),
    *NM_PROMOTION_RULES,
    *NM_DIMENSION_RULES,
)

_INSERT = """
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


def seed_conformance_nm(connection: psycopg.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT, [_row(rule) for rule in NM_RULES])
        cursor.execute(
            "select count(*) from lineage.conformance_rules where source_id like 'nm\\_ocd\\_%%'"
        )
        return int(cursor.fetchone()[0])
