"""The NM OCD conformance registry (SB-07 §6.2), appended to in phase order.

Phase 1 seeds the retrieval decisions: what the artifact is called, where it comes from, and
why glasswell stamps its own vintage on it. Rule ids are immutable — a correction is a new row
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


NM_RULES: tuple[dict[str, object], ...] = tuple(
    family(table) for table, _ in NM_TABLES for family in (_undated_vintage, _ftp_layout, _host_pin)
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
