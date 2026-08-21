"""The NM OCD conformance registry (SB-07 §6.2), appended to in phase order.

Phase 1 seeds the retrieval decisions: what the artifact is called, where it comes from, and
why glasswell stamps its own vintage on it. Phase 2 adds the parse decisions: the record tag and
namespace, the encoding, the header each source declares, and the CHAR widths that make a code
look like a code only after a declared trim. Rule ids are immutable — a correction is a new row
with `supersedes_rule_id`, never an edit (R8).

`load_rules` reads one `source_id` per call, so every family is instantiated per source: a row
seeded on `nm_ocd_wcproduction` is invisible to a `nm_ocd_pool` load, and a derivation citing
another source's rule id would be a lineage claim glasswell cannot resolve.
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


NM_RULES: tuple[dict[str, object], ...] = (
    *(
        family(table)
        for table, _ in NM_TABLES
        for family in (_undated_vintage, _ftp_layout, _host_pin, _parse, _pad)
    ),
    _mod_dte(),
    _month(),
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
