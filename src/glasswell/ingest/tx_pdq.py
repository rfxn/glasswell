"""Acquire the RRC PDQ dump once, and read it from disk in as many passes as the job needs.

The archive is 3.65 GB behind a GoAnywhere postback that ignores `Range`, so there is no
resume and a partial fetch fails the run rather than promoting a truncated member. That is not
a streaming problem, because glasswell does not stream: `lineage/fetch.py` writes every fetch
to a file in the raw zone, which is `/data` on the host and holds no relation file. The parse
is therefore random access over a local artifact, sealed `0o444` so a second pass cannot
corrupt it, and widening the scope later is a re-parse rather than a re-fetch.

Two passes, one manifest. Pass one reads the three small general-purpose members and the
crosswalk, and builds the county allowlist; pass two reads the lease member and is the next
phase's. `OG_LEASE_CYCLE` carries no county, which is why `cr_tx_pdq_scope_1` applies the
scope at promotion and not here.
"""

from __future__ import annotations

import argparse
import json
import os
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import psycopg
from psycopg.rows import dict_row

from glasswell.db.dsn import add_dsn_argument, resolve_dsn
from glasswell.ingest.base import resolve_environment
from glasswell.ingest.tx_mft import MftClient
from glasswell.lineage import (
    ConformanceRule,
    InputRef,
    OutputSpec,
    PostgresRecorder,
    current_session,
    derive,
    fetch_raw,
    lineage_session,
    load_rules,
    quarantine,
)
from glasswell.lineage.audit import emit
from glasswell.lineage.conformance import rule_for_family
from glasswell.lineage.fetch import resolve_raw_root
from glasswell.lineage.fetch_attempts import durable_fetch_attempts
from glasswell.lineage.serialization import hash_payload
from glasswell.seed.conformance_tx import PDQ_MEMBER_LAYOUT

SOURCE_ID = "tx_pdq_dsv"
SOURCE_KEY = "PDQ_DSV.zip"
PDQ_LINK = "https://mft.rrc.texas.gov/link/1f5ddb8d-329a-4459-b7f8-177b4f5ee60d"

W10_SOURCE_ID = "tx_w10_wlf607"
G10_SOURCE_ID = "tx_g10_gse10"

# Families, never versions: a restatement changes the id, and cr_tx_pdq_format_2 is what
# retires cr_tx_pdq_format_1 the moment it seeds.
FORMAT_FAMILY = "cr_tx_pdq_format"
ARCHIVE_FAMILY = "cr_tx_well_status_archive"
SCOPE_FAMILY = "cr_tx_pdq_scope"
CROSSWALK_FAMILY = "cr_tx_pdq_crosswalk"
LIQUIDS_FAMILY = "cr_tx_liquids_basis"
GAS_FAMILY = "cr_tx_gas_basis"
GRAIN_FAMILY = "cr_tx_production_grain"
API10_FAMILY = "cr_tx_api10_build"

COUNTY_MEMBER = "GP_COUNTY_DATA_TABLE.dsv"
DATE_RANGE_MEMBER = "GP_DATE_RANGE_CYCLE_DATA_TABLE.dsv"
DISTRICT_MEMBER = "GP_DISTRICT_DATA_TABLE.dsv"
LEASE_CYCLE_MEMBER = "OG_LEASE_CYCLE_DATA_TABLE.dsv"
WELL_COMPLETION_MEMBER = "OG_WELL_COMPLETION_DATA_TABLE.dsv"
REGULATORY_LEASE_MEMBER = "OG_REGULATORY_LEASE_DW_DATA_TABLE.dsv"

DELIMITER = "}"
BATCH_ROWS = 20_000

# canonical.production_monthly's volume is numeric(18,3), so fifteen integral digits is the
# ceiling. A PDQ volume is NUMBER(9), which fits; anything wider is not a volume this schema
# can hold and is quarantined rather than truncated into a number that looks filed.
VOLUME_CEILING = Decimal(10) ** 15

# The lease-month's four volume columns, and which canonical stream each becomes. The two
# liquid columns are disjoint populations keyed by OIL_GAS_CODE, so their union double-counts
# nothing; the two gas-lift columns are injection and are never read.
STREAM_COLUMNS: tuple[tuple[str, str, str, str], ...] = (
    ("lease_oil_prod_vol", "oil", "bbl", "O"),
    ("lease_cond_prod_vol", "condensate", "bbl", "G"),
    ("lease_gas_prod_vol", "gas", "mcf", "G"),
    ("lease_csgd_prod_vol", "gas", "mcf", "O"),
)


def _staging_columns(member: str) -> tuple[str, ...]:
    """The staging columns of a member: the subset cr_tx_pdq_format_2 lists as consumed, cased
    as the tables spell it. Read from the registry rather than typed here, because a column
    list typed twice is what left the completion member three columns short of the file."""
    return tuple(name.lower() for name in PDQ_MEMBER_LAYOUT[member]["consumed"])


LEASE_CYCLE_COLUMNS = _staging_columns(LEASE_CYCLE_MEMBER)
COMPLETION_COLUMNS = _staging_columns(WELL_COMPLETION_MEMBER)
REGULATORY_COLUMNS = _staging_columns(REGULATORY_LEASE_MEMBER)

# The runbook's own gate, restated where the code that would fill the disk can read it.
PGDATA_GATE_BYTES = 40 * 1024**3
# Content-Length measured on the wire 2026-09-03T00:44:46Z; the listing said 3.40 GB and the
# server answered a Range request with 200 and the full length, so there is no resume. The
# precheck wants room for this and for the vintage retained beside it, because the raw zone
# accretes on purpose: nothing sweeps an artifact.
ARCHIVE_BYTES_MEASURED = 3_652_221_981


class ArchiveFormatError(RuntimeError):
    """A member's header is not the header the format rule describes, so nothing is promoted."""


class FilesystemPrecheckError(RuntimeError):
    """The raw zone cannot take the artifact, or its staging area is on another device."""


@dataclass(frozen=True, slots=True)
class MemberLayout:
    """The header the rule in force describes for each member, and the rule that describes it.

    Built from the registry, never from the archive: a layout read out of the file it is meant
    to judge would agree with every file.
    """

    rule_id: str
    members: Mapping[str, Mapping[str, Sequence[str]]]

    def header_for(self, member: str) -> tuple[str, ...]:
        described = self.members.get(member)
        if described is None:
            raise ArchiveFormatError(
                f"{member}: {self.rule_id} describes no layout for this member"
            )
        return tuple(str(column) for column in described["header"])


def member_layout(format_rule: ConformanceRule) -> MemberLayout:
    """The layout the rule in force publishes, held to the one this tree consumes.

    Two clocks reach a header -- the rule row a database was seeded with, and the registry this
    module projects its staging columns from. A database seeded by an older tree would judge
    the header against one and read the row against the other, and the disagreement would
    surface as a KeyError on a column nobody named.
    """
    published = format_rule.spec.get("members")
    if not published:
        raise ArchiveFormatError(
            f"{format_rule.rule_id} publishes no member layout; the database's rules predate"
            " the layout restatement and nothing here may be parsed against them"
        )
    registered = {
        member: {"header": list(layout["header"]), "consumed": list(layout["consumed"])}
        for member, layout in PDQ_MEMBER_LAYOUT.items()
    }
    if published != registered:
        moved = sorted(set(published) ^ set(registered)) or sorted(
            member for member in registered if published.get(member) != registered[member]
        )
        raise ArchiveFormatError(
            f"{format_rule.rule_id} describes a layout this tree does not register, at"
            f" {', '.join(moved)}: seed the rules this code was written against before loading"
        )
    return MemberLayout(format_rule.rule_id, published)


@dataclass(frozen=True, slots=True)
class MemberInventory:
    name: str
    compressed: int
    uncompressed: int

    def to_dict(self) -> dict[str, int | str]:
        return {
            "member": self.name,
            "compressed": self.compressed,
            "uncompressed": self.uncompressed,
        }


@dataclass(frozen=True, slots=True)
class CrosswalkLoad:
    manifest_id: str
    parse_derivation_id: str
    membership_derivation_id: str
    staged_completions: int
    staged_regulatory_leases: int
    membership_rows: int
    api10s: int
    api10s_with_two_lease_keys: int
    lease_keys: int
    in_scope_lease_keys: int
    lease_parse_derivation_id: str = ""
    lease_rows_staged: int = 0
    lease_promotion: Mapping[str, int] = field(default_factory=dict)
    members: tuple[MemberInventory, ...] = field(default_factory=tuple)
    window: tuple[str, str] | None = None
    precheck: Mapping[str, Any] = field(default_factory=dict)
    unchanged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": SOURCE_ID,
            "manifest_id": self.manifest_id,
            "staged_completions": self.staged_completions,
            "staged_regulatory_leases": self.staged_regulatory_leases,
            "membership_rows": self.membership_rows,
            "lease_rows_staged": self.lease_rows_staged,
            "lease_promotion": dict(self.lease_promotion),
            "api10s": self.api10s,
            "api10s_with_two_lease_keys": self.api10s_with_two_lease_keys,
            "lease_keys": self.lease_keys,
            "in_scope_lease_keys": self.in_scope_lease_keys,
            "members": [member.to_dict() for member in self.members],
            "window": list(self.window) if self.window else None,
            "precheck": dict(self.precheck),
            "unchanged": self.unchanged,
        }


def rule(connection: psycopg.Connection, family: str, source_id: str = SOURCE_ID
         ) -> ConformanceRule:
    """The rule in force for a family. Pinning an id would miss its own restatement."""
    return rule_for_family(load_rules(connection, source_id=source_id), family)


def precheck_filesystems(
    raw_root: Path | str | None = None,
    *,
    needed: int = 2 * ARCHIVE_BYTES_MEASURED,
    pgdata: Path | str | None = None,
) -> dict[str, Any]:
    """The raw zone has room, and its `.incoming` is on the same device as its destination.

    `fetch.py` writes to `<root>/.incoming` and then `os.replace`s into place, which is a rename
    and cannot cross a device. Had the temporary file been on `/tmp` — the 145 GB root disk on
    this host — a 3.65 GB fetch would fill the root volume and then fail the rename, having
    already spent the download.
    """
    root = resolve_raw_root(raw_root)
    root.mkdir(parents=True, exist_ok=True)
    incoming = root / ".incoming"
    incoming.mkdir(parents=True, exist_ok=True)

    if os.stat(root).st_dev != os.stat(incoming).st_dev:
        raise FilesystemPrecheckError(
            f"{incoming} is on a different device from {root}: the staged rename would fail"
            " after the whole artifact had been downloaded"
        )
    available = _available(root)
    if needed and available < needed:
        raise FilesystemPrecheckError(
            f"{root} has {available} bytes available and the artifact needs {needed}"
        )
    report: dict[str, Any] = {
        "raw_root": str(root),
        "available_bytes": available,
        "needed_bytes": needed,
        "same_device": True,
    }
    if pgdata is not None:
        # The runbook's gate, asserted before the fetch rather than discovered half way through
        # a promotion: canonical is append-only and a half-promoted vintage is a state somebody
        # has to reason about.
        headroom = _available(Path(pgdata))
        if headroom < PGDATA_GATE_BYTES:
            raise FilesystemPrecheckError(
                f"{pgdata} has {headroom} bytes available, below the {PGDATA_GATE_BYTES}"
                " the runbook stops and escalates at"
            )
        report["pgdata"] = str(pgdata)
        report["pgdata_available_bytes"] = headroom
    return report


def _available(path: Path) -> int:
    usage = os.statvfs(path)
    return usage.f_bavail * usage.f_frsize


def member_inventory(path: Path) -> tuple[MemberInventory, ...]:
    """Every member's compressed and uncompressed size, from the archive's central directory.

    Read before anything is parsed: member order and member size do not constrain a
    random-access read, but they are what tells an operator whether the file they were handed
    is the file the format rule describes.
    """
    with zipfile.ZipFile(path) as archive:
        return tuple(
            MemberInventory(
                name=info.filename, compressed=info.compress_size, uncompressed=info.file_size
            )
            for info in archive.infolist()
        )


def _refuse_unless_described(member: str, header: Sequence[str], layout: MemberLayout) -> None:
    """A header that is not the one the rule describes, refused by name and never by width.

    Names, because a width check passes a renamed column and a reorder, and both re-map every
    row while nothing failed to parse. Positions too: the rule states an order it measured, and
    a member that reordered is no longer the member it describes even where the read survives.
    """
    described = layout.header_for(member)
    if tuple(header) == described:
        return
    absent = [column for column in described if column not in header]
    unlisted = [column for column in header if column not in described]
    faults = []
    if absent:
        faults.append(f"does not carry {', '.join(absent)}")
    if unlisted:
        faults.append(f"carries {', '.join(unlisted)}, which the rule does not list")
    if not faults and len(header) != len(described):
        faults.append(f"repeats a column across {len(header)} against the rule's {len(described)}")
    if not faults:
        faults.append("reorders " + ", ".join(
            f"{found} where the rule has {wanted}"
            for found, wanted in zip(header, described, strict=True)
            if found != wanted
        ))
    raise ArchiveFormatError(f"{member}: the header {' and '.join(faults)} ({layout.rule_id})")


def _member_rows(
    archive: zipfile.ZipFile, member: str, layout: MemberLayout
) -> Iterator[dict[str, str]]:
    """One dict per data row, keyed by the member's own header, judged against the rule's.

    A header that is not the one the rule describes refuses: a schema change invalidates the
    row mapping rather than one row, so nothing failed to parse and there is nothing to
    quarantine. A column the rule lists and the parse does not consume is read past on purpose.
    """
    with archive.open(member) as handle:
        header: list[str] | None = None
        for raw in handle:
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if header is None:
                header = line.split(DELIMITER)
                _refuse_unless_described(member, header, layout)
                continue
            if not line:
                continue
            values = line.split(DELIMITER)
            if len(values) != len(header):
                raise ArchiveFormatError(
                    f"{member}: a row carries {len(values)} fields against a"
                    f" {len(header)}-column header"
                )
            yield dict(zip(header, values, strict=True))


def lease_key(oil_gas_code: str, district_no: str, lease_no: str) -> str:
    """`cr_tx_lease_key_1`'s key, padded before any comparison.

    LEASE_NO is VARCHAR2(6) in PDQ, PIC 9(5) in the W-10 file and padded to six in the EWA
    export, and bare LEASE_NO collides on 33,868 of 348,293 leases, so the district and the
    oil-gas code are both in the key.
    """
    return f"{oil_gas_code.strip()}-{district_no.strip()}-{lease_no.strip().zfill(6)}"


def api10_from(county_code: str, unique_no: str, *, state_code: str = "42") -> str | None:
    county = county_code.strip()
    unique = unique_no.strip()
    if not county.isdigit() or not unique.isdigit():
        return None
    return f"{state_code}{county.zfill(3)}{unique.zfill(5)}"


def production_window(
    archive: zipfile.ZipFile, layout: MemberLayout
) -> tuple[str, str] | None:
    """The dump's own statement of what it covers, read rather than assumed."""
    for row in _member_rows(archive, DATE_RANGE_MEMBER, layout):
        return (
            row["OLDEST_PROD_CYCLE_YEAR_MONTH"].strip(),
            row["NEWEST_PROD_CYCLE_YEAR_MONTH"].strip(),
        )
    return None


def district_labels(archive: zipfile.ZipFile, layout: MemberLayout) -> dict[str, str]:
    """`DISTRICT_NO` to `DISTRICT_NAME`, which are two vocabularies and not one.

    District 10 is named 08 and district 08 is named 7B, so a join on the name silently crosses
    districts. The map is read so it can be recorded, never so it can be joined on.
    """
    return {
        row["DISTRICT_NO"].strip(): row["DISTRICT_NAME"].strip()
        for row in _member_rows(archive, DISTRICT_MEMBER, layout)
    }


_INSERT_COMPLETION = (
    "insert into staging.tx_pdq_well_completion (manifest_id, source_row_ordinal, "
    + ", ".join(COMPLETION_COLUMNS)
    + ") values (%(manifest_id)s, %(source_row_ordinal)s, "
    + ", ".join(f"%({column})s" for column in COMPLETION_COLUMNS)
    + ") on conflict (manifest_id, source_row_ordinal) do nothing"
)

_INSERT_REGULATORY = (
    "insert into staging.tx_pdq_regulatory_lease (manifest_id, source_row_ordinal, "
    + ", ".join(REGULATORY_COLUMNS)
    + ") values (%(manifest_id)s, %(source_row_ordinal)s, "
    + ", ".join(f"%({column})s" for column in REGULATORY_COLUMNS)
    + ") on conflict (manifest_id, source_row_ordinal) do nothing"
)

_INSERT_MEMBERSHIP = """
insert into canonical.lease_membership
    (jurisdiction_code, lease_key, api10, link_role, source_id, effective_from,
     source_manifest_id, derivation_id)
values ('TX', %(lease_key)s, %(api10)s, 'canonical_crosswalk', %(source_id)s,
        %(effective_from)s, %(manifest_id)s, %(derivation_id)s)
on conflict do nothing
"""

# Rebuilt for the day it measures rather than upserted: a mart is rebuilt, and a re-run that
# measured the same population again should say so with its own derivation rather than leaving
# the first run's id beside the second run's number.
_CLEAR_CENSUS = """
delete from marts.tx_allocation_census
 where measured_on = %(measured_on)s and measure = any(%(measures)s)
"""

_INSERT_CENSUS = """
insert into marts.tx_allocation_census (measure, measured_on, value, derivation_id)
values (%(measure)s, %(measured_on)s, %(value)s, %(derivation_id)s)
"""


def _stage_members(
    connection: psycopg.Connection,
    archive: zipfile.ZipFile,
    manifest_id: str,
    *,
    layout: MemberLayout,
) -> tuple[str, int, int]:
    """Pass one's writes: the crosswalk and the lease dimension, column-projected and unfiltered.

    Unfiltered on purpose. The county scope is a promotion decision, and a parse that dropped
    rows would make the staged bytes disagree with the artifact their manifest names.
    """
    staged_completions = 0
    staged_regulatory = 0
    with connection.cursor() as cursor:
        batch: list[dict[str, Any]] = []
        for ordinal, row in enumerate(
            _member_rows(archive, WELL_COMPLETION_MEMBER, layout)
        ):
            batch.append(
                {
                    "manifest_id": manifest_id,
                    "source_row_ordinal": ordinal,
                    **{column: row[column.upper()].strip() or None
                       for column in COMPLETION_COLUMNS},
                }
            )
            staged_completions += 1
            if len(batch) >= BATCH_ROWS:
                cursor.executemany(_INSERT_COMPLETION, batch)
                batch.clear()
        if batch:
            cursor.executemany(_INSERT_COMPLETION, batch)

        batch = []
        for ordinal, row in enumerate(
            _member_rows(archive, REGULATORY_LEASE_MEMBER, layout)
        ):
            batch.append(
                {
                    "manifest_id": manifest_id,
                    "source_row_ordinal": ordinal,
                    **{column: row[column.upper()].strip() or None
                       for column in REGULATORY_COLUMNS},
                }
            )
            staged_regulatory += 1
            if len(batch) >= BATCH_ROWS:
                cursor.executemany(_INSERT_REGULATORY, batch)
                batch.clear()
        if batch:
            cursor.executemany(_INSERT_REGULATORY, batch)

    with derive(
        "stage.parse",
        output=OutputSpec(
            store="postgres",
            dataset="staging.tx_pdq_well_completion",
            partition={"manifest_id": manifest_id},
        ),
        params={
            "format_rule": layout.rule_id,
            "members": [WELL_COMPLETION_MEMBER, REGULATORY_LEASE_MEMBER],
            "pass": 1,
        },
        inputs=[InputRef(kind="manifest", ref_id=manifest_id)],
        rules=[layout.rule_id],
    ) as context:
        context.set_rows(staged_completions + staged_regulatory)
        context.set_output_hash(
            hash_payload(
                {
                    "completions": staged_completions,
                    "regulatory_leases": staged_regulatory,
                    "manifest_id": manifest_id,
                }
            )
        )
    return context.derivation_id, staged_completions, staged_regulatory


def scope_allowlist(
    connection: psycopg.Connection, manifest_id: str, counties: Sequence[str]
) -> set[str]:
    """The in-scope lease keys, derived from the crosswalk because the lease member has no county.

    This is the whole reason the scope is applied at promotion: a lease is in scope when one of
    its wells is, and only `OG_WELL_COMPLETION` says where a well is.
    """
    admitted = {str(code) for code in counties}
    with connection.cursor() as cursor:
        cursor.execute(
            "select distinct oil_gas_code, district_no, lease_no from"
            " staging.tx_pdq_well_completion"
            " where manifest_id = %s and api_county_code = any(%s)",
            (manifest_id, sorted(admitted)),
        )
        return {lease_key(*row) for row in cursor.fetchall()}


def _promote_membership(
    connection: psycopg.Connection,
    manifest_id: str,
    *,
    parse_derivation_id: str,
    vintage: date,
    crosswalk_rule: ConformanceRule,
    api10_rule: ConformanceRule,
) -> tuple[str, int, dict[str, int]]:
    """The crosswalk as `canonical.lease_membership` rows, one per (lease, well).

    A wellbore completed on an oil lease and a gas lease has two lease keys in one dump and
    therefore two rows. They are not duplicates to collapse: they are the thing being
    allocated, and folding them would make the share's lease ambiguous.
    """
    state_code = str(api10_rule.spec["state_code"])
    with connection.cursor() as cursor:
        cursor.execute(
            "select oil_gas_code, district_no, lease_no, api_county_code, api_unique_no"
            "  from staging.tx_pdq_well_completion where manifest_id = %s",
            (manifest_id,),
        )
        pairs: set[tuple[str, str]] = set()
        for code, district, lease, county, unique in cursor.fetchall():
            api10 = api10_from(county or "", unique or "", state_code=state_code)
            if api10 is None or not (code and district and lease):
                continue
            pairs.add((lease_key(code, district, lease), api10))

    by_api: dict[str, set[str]] = {}
    for key, api10 in pairs:
        by_api.setdefault(api10, set()).add(key)
    measurements = {
        "api10s": len(by_api),
        "api10s_with_two_lease_keys": sum(1 for keys in by_api.values() if len(keys) > 1),
        "lease_keys": len({key for key, _ in pairs}),
    }

    with derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset="canonical.lease_membership",
            partition={"manifest_id": manifest_id, "jurisdiction_code": "TX"},
        ),
        params={"link_role": "canonical_crosswalk", "merge_forbidden": True, **measurements},
        inputs=[
            InputRef(kind="derivation", ref_id=parse_derivation_id),
            InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage),
        ],
        rules=[crosswalk_rule.rule_id, api10_rule.rule_id],
    ) as context:
        context.set_rows(len(pairs))
        context.set_output_hash(
            hash_payload({"pairs": sorted(f"{key}/{api10}" for key, api10 in pairs)})
        )

    with connection.cursor() as cursor:
        cursor.executemany(
            _INSERT_MEMBERSHIP,
            [
                {
                    "lease_key": key,
                    "api10": api10,
                    "source_id": SOURCE_ID,
                    "effective_from": vintage,
                    "manifest_id": manifest_id,
                    "derivation_id": context.derivation_id,
                }
                for key, api10 in sorted(pairs)
            ],
        )
        inserted = max(cursor.rowcount, 0)
    return context.derivation_id, inserted, measurements


def record_census(
    connection: psycopg.Connection,
    measurements: Mapping[str, float],
    *,
    measured_on: date,
    derivation_id: str,
) -> int:
    """Every figure this load measured, dated, so R-5 sees the population move.

    They live here rather than inside a rule row because a rule row cannot be re-measured: the
    EWA scale figures are in the rule that measured them, and these are measured by the load.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            _CLEAR_CENSUS,
            {"measured_on": measured_on, "measures": sorted(measurements)},
        )
        cursor.executemany(
            _INSERT_CENSUS,
            [
                {
                    "measure": measure,
                    "measured_on": measured_on,
                    "value": value,
                    "derivation_id": derivation_id,
                }
                for measure, value in sorted(measurements.items())
            ],
        )
    return len(measurements)


@contextmanager
def _staging_outcome_recorded(
    connection: psycopg.Connection, manifest_id: str, *, rule_id: str
) -> Iterator[None]:
    """Record what became of the artifact, whatever ends the run between here and its commit.

    The fetch is a fact and is already committed, so the poll finalises `new` -- truthfully, the
    bytes landed. Nothing then says the load did not happen, and `/status` would read the stage
    as a current source with a fresh retrieval vintage. `KeyboardInterrupt` and `SystemExit` are
    `BaseException` and stay outside this: an operator's Ctrl-C is not a staging failure.
    """
    try:
        yield
    except Exception as failure:
        _record_staging_failure(connection, manifest_id, failure, rule_id=rule_id)
        raise


def _record_staging_failure(
    connection: psycopg.Connection, manifest_id: str, failure: Exception, *, rule_id: str
) -> None:
    """The failure, on its own commit, against the manifest whose artifact was not loaded.

    The reason code is the exception's own name, so this stays truthful for a header refusal, a
    memory kill or a database error without being told which it was. Whatever the run staged is
    rolled back first: a half-written member is not a fact about anything.
    """
    connection.rollback()
    session = current_session()
    emit(
        connection,
        "staging.load_failed",
        subject_type="manifest",
        subject_id=manifest_id,
        payload={
            "source_id": SOURCE_ID,
            "reason_code": type(failure).__name__.lower(),
            "rule_id": rule_id,
            "detail": str(failure),
        },
        correlation_id=session.correlation_id,
        occurred_at=session.clock.now(),
    )
    connection.commit()


def _record_staging_load(
    connection: psycopg.Connection, manifest_id: str, derivation_id: str
) -> None:
    """Both passes read the artifact through, so the manifest names the derivation that did it.

    003_manifests.sql declared `staging_load_ref` and nothing ever set it or wrote down what
    it meant; the column comment 083 adds is where that meaning now lives. Its absence on a
    head manifest is what lets status.source_health tell a fetch that was parsed from one that
    was only fetched.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "update lineage.manifests set staging_load_ref = %s where manifest_id = %s",
            (derivation_id, manifest_id),
        )


def load(
    connection: psycopg.Connection,
    *,
    url: str | None = None,
    raw_root: Path | str | None = None,
    client: httpx.Client | None = None,
    restage: bool = False,
    pgdata: Path | str | None = None,
    expect_bytes: int = ARCHIVE_BYTES_MEASURED,
    promote_years: Sequence[int] | None = None,
    stage_only: bool = False,
) -> CrosswalkLoad:
    """Fetch the archive once and read pass one from the stored bytes.

    `expect_bytes` is what the raw zone is prechecked against, doubled because the vintage
    beside the new one is retained on purpose: nothing sweeps a raw artifact, so a monthly
    cadence adds 43.8 GB a year to /data and that is the behaviour 4E.5 asks for.
    """
    format_rule = rule(connection, FORMAT_FAMILY)
    layout = member_layout(format_rule)
    scope_rule = rule(connection, SCOPE_FAMILY)
    crosswalk_rule = rule(connection, CROSSWALK_FAMILY)
    liquids_rule = rule(connection, LIQUIDS_FAMILY)
    gas_rule = rule(connection, GAS_FAMILY)
    grain_rule = rule(connection, GRAIN_FAMILY)
    api10_rule = rule(connection, API10_FAMILY, source_id="tx_gis_wells_county")

    precheck = precheck_filesystems(
        raw_root, needed=2 * expect_bytes, pgdata=pgdata
    )
    fetched = fetch_raw(
        connection,
        SOURCE_ID,
        SOURCE_KEY,
        url=url or f"{PDQ_LINK}?filename={SOURCE_KEY}",
        acquisition_method="mft_guid_resolve",
        raw_root=raw_root,
        client=client,
        media_type="application/zip",
        rules=[format_rule.rule_id],
        decompressed_inventory=lambda path: [
            member.to_dict() for member in member_inventory(path)
        ],
    )
    # A completed fetch is a fact and the parse is a separate outcome, so the manifest is
    # committed the moment the bytes are placed. Held to the end of load(), a refusal below
    # rolled it back and left 3.65 GB sealed on disk with no row naming it -- and because
    # stage_payload() reuses a slot only through owning_slot(), the re-run placed a second copy.
    connection.commit()
    manifest = fetched.manifest
    # Everything after the fetch commit is inside this: `_record_staging_load` is stamped in
    # this same transaction, so a promotion that fails unstamps it as surely as a refusal.
    with _staging_outcome_recorded(connection, manifest.manifest_id, rule_id=layout.rule_id):
        members = member_inventory(fetched.payload_path)
        if restage:
            with connection.cursor() as cursor:
                for table in (
                    "tx_pdq_well_completion", "tx_pdq_regulatory_lease", "tx_pdq_lease_cycle"
                ):
                    cursor.execute(
                        f"delete from staging.{table} where manifest_id = %s",
                        (manifest.manifest_id,),
                    )
        with zipfile.ZipFile(fetched.payload_path) as archive:
            window = production_window(archive, layout)
            districts = district_labels(archive, layout)
            parse_id, completions, regulatory = _stage_members(
                connection, archive, manifest.manifest_id, layout=layout
            )
            lease_parse_id, lease_rows = stage_lease_cycle(
                connection, archive, manifest.manifest_id, layout=layout
            )
        _record_staging_load(connection, manifest.manifest_id, lease_parse_id)

        vintage = manifest.fetch_vintage
        membership_id, membership_rows, measurements = _promote_membership(
            connection,
            manifest.manifest_id,
            parse_derivation_id=parse_id,
            vintage=vintage,
            crosswalk_rule=crosswalk_rule,
            api10_rule=api10_rule,
        )
        allowlist = scope_allowlist(
            connection, manifest.manifest_id, scope_rule.spec["county_codes"]
        )
        promotion: dict[str, int] = {}
        if not stage_only:
            years = promote_years if promote_years is not None else _staged_years(
                connection, manifest.manifest_id
            )
            for year in years:
                # Per calendar year, with the headroom asserted before each append rather than
                # discovered inside one: canonical is append-only and a half-promoted vintage is a
                # state somebody has to reason about.
                if pgdata is not None:
                    precheck_filesystems(raw_root, needed=0, pgdata=pgdata)
                _, measured = promote_lease_cycle(
                    connection,
                    manifest.manifest_id,
                    parse_derivation_id=lease_parse_id,
                    vintage=vintage,
                    allowlist=allowlist,
                    scope_rule=scope_rule,
                    liquids_rule=liquids_rule,
                    gas_rule=gas_rule,
                    grain_rule=grain_rule,
                    years=[year],
                )
                for measure, value in measured.items():
                    promotion[measure] = promotion.get(measure, 0) + value
                promotion["high_water_year"] = year

        session = current_session()
        emit(
            connection,
            "staging.scope_excluded",
            subject_type="manifest",
            subject_id=manifest.manifest_id,
            payload={
                "rows_excluded": 0,
                "rows_staged": completions + regulatory,
                "scope_rule": scope_rule.rule_id,
                "lease_keys_in_scope": len(allowlist),
                "lease_keys_total": measurements["lease_keys"],
                "note": (
                    "the crosswalk is staged unfiltered and the scope is applied at promotion,"
                    " because OG_LEASE_CYCLE carries no county"
                ),
            },
            correlation_id=session.correlation_id,
            occurred_at=session.clock.now(),
        )
        record_census(
            connection,
            {
                "crosswalk_api10s": measurements["api10s"],
                "crosswalk_api10s_with_two_lease_keys": measurements["api10s_with_two_lease_keys"],
                "crosswalk_lease_keys": measurements["lease_keys"],
                "crosswalk_lease_keys_in_scope": len(allowlist),
                "districts_published": len(districts),
                "lease_months_staged": lease_rows,
                "lease_rows_promoted": promotion.get("rows_appended", 0),
            },
            measured_on=vintage,
            derivation_id=membership_id,
        )
        return CrosswalkLoad(
            manifest_id=manifest.manifest_id,
            parse_derivation_id=parse_id,
            membership_derivation_id=membership_id,
            staged_completions=completions,
            staged_regulatory_leases=regulatory,
            membership_rows=membership_rows,
            lease_parse_derivation_id=lease_parse_id,
            lease_rows_staged=lease_rows,
            lease_promotion=promotion,
            api10s=measurements["api10s"],
            api10s_with_two_lease_keys=measurements["api10s_with_two_lease_keys"],
            lease_keys=measurements["lease_keys"],
            in_scope_lease_keys=len(allowlist),
            members=members,
            window=window,
            precheck=precheck,
            unchanged=bool(fetched.unchanged) and not restage,
        )


_INSERT_LEASE_CYCLE = (
    "insert into staging.tx_pdq_lease_cycle (manifest_id, source_row_ordinal, "
    + ", ".join(LEASE_CYCLE_COLUMNS)
    + ") values (%(manifest_id)s, %(source_row_ordinal)s, "
    + ", ".join(f"%({column})s" for column in LEASE_CYCLE_COLUMNS)
    + ") on conflict (manifest_id, source_row_ordinal) do nothing"
)

_INSERT_CANONICAL = """
insert into canonical.production_monthly (
    entity_type, entity_key, reporting_level, api10, production_month, stream, source_id,
    report_vintage, volume, unit, granularity, null_semantics, value_hash, source_manifest_id,
    derivation_id)
values ('lease', %(entity_key)s, 'lease', null, %(production_month)s, %(stream)s, %(source_id)s,
        %(report_vintage)s, %(volume)s, %(unit)s, 'lease_reported', %(null_semantics)s,
        %(value_hash)s, %(manifest_id)s, %(derivation_id)s)
on conflict do nothing
"""

_STAGED_LEASE_ROWS = (
    "select source_row_ordinal, " + ", ".join(LEASE_CYCLE_COLUMNS)
    + " from staging.tx_pdq_lease_cycle where manifest_id = %(manifest_id)s"
    + " and (%(years)s::text[] is null or left(cycle_year_month, 4) = any(%(years)s))"
    + " order by source_row_ordinal"
)


def stage_lease_cycle(
    connection: psycopg.Connection,
    archive: zipfile.ZipFile,
    manifest_id: str,
    *,
    layout: MemberLayout,
) -> tuple[str, int]:
    """Pass two: the lease member, column-projected and unfiltered.

    Unfiltered because the county lives in the crosswalk and not here, and column-projected
    because the member carries allowables, balances and dispositions this track promotes
    nothing from. Both passes read the same on-disk artifact under one manifest and one sha256.
    """
    staged = 0
    with connection.cursor() as cursor:
        batch: list[dict[str, Any]] = []
        for ordinal, row in enumerate(
            _member_rows(archive, LEASE_CYCLE_MEMBER, layout)
        ):
            batch.append(
                {
                    "manifest_id": manifest_id,
                    "source_row_ordinal": ordinal,
                    **{column: row[column.upper()].strip() or None
                       for column in LEASE_CYCLE_COLUMNS},
                }
            )
            staged += 1
            if len(batch) >= BATCH_ROWS:
                cursor.executemany(_INSERT_LEASE_CYCLE, batch)
                batch.clear()
        if batch:
            cursor.executemany(_INSERT_LEASE_CYCLE, batch)

    with derive(
        "stage.parse",
        output=OutputSpec(
            store="postgres",
            dataset="staging.tx_pdq_lease_cycle",
            partition={"manifest_id": manifest_id},
        ),
        params={"format_rule": layout.rule_id, "member": LEASE_CYCLE_MEMBER, "pass": 2},
        inputs=[InputRef(kind="manifest", ref_id=manifest_id)],
        rules=[layout.rule_id],
    ) as context:
        context.set_rows(staged)
        context.set_output_hash(hash_payload({"rows": staged, "manifest_id": manifest_id}))
    return context.derivation_id, staged


def production_month(cycle_year_month: str | None) -> date | None:
    """`YYYYMM` as the month's first day, which is how canonical keys a production month."""
    text = (cycle_year_month or "").strip()
    if len(text) != 6 or not text.isdigit():
        return None
    year, month = int(text[:4]), int(text[4:])
    if not 1 <= month <= 12:
        return None
    return date(year, month, 1)


def _volume(raw: str | None) -> tuple[Decimal | None, str | None]:
    """The filed volume, or the reason it is not one.

    A negative value is a correction the operator filed and is promoted as one: the RRC says
    production information may change as revised, corrected or delinquent reports arrive, and
    a correction dropped here would leave the lease's history overstated for ever.
    """
    text = (raw or "").strip()
    if not text:
        return None, None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None, "impossible_volume"
    if abs(value) >= VOLUME_CEILING:
        return None, "impossible_volume"
    return value, None


def _null_semantics(filed_flag: str | None, volume: Decimal | None) -> str:
    """A filed zero and an unfiled month are two different facts and are never collapsed.

    PROD_REPORT_FILED_FLAG is the operator's own statement that a report exists for the month,
    so a zero under it is a reported zero and a blank without it is a month nobody filed.
    """
    filed = (filed_flag or "").strip().upper() == "Y"
    if not filed:
        return "no_report"
    if volume is None:
        return "no_report"
    return "reported_zero" if volume == 0 else "reported"


def _lease_records(
    row: Mapping[str, Any], *, allowlist: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    """One canonical row per filed stream, or the reason the lease-month produced none."""
    code = (row["oil_gas_code"] or "").strip()
    district = (row["district_no"] or "").strip()
    lease_no = (row["lease_no"] or "").strip()
    month = production_month(row["cycle_year_month"])
    if not (code and district and lease_no):
        return [], [], "key_incomplete"
    if month is None:
        return [], [], "out_of_range_date"
    key = lease_key(code, district, lease_no)
    if key not in allowlist:
        return [], [], "out_of_scope"

    records: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    for column, stream, unit, owning_code in STREAM_COLUMNS:
        if code != owning_code:
            continue
        volume, reason = _volume(row[column])
        if reason is not None:
            rejects.append(
                {
                    "source_row_ordinal": row["source_row_ordinal"],
                    "entity_key": key,
                    "production_month": month.isoformat(),
                    "stream": stream,
                    "column": column,
                    "value": row[column],
                    "reason_code": reason,
                }
            )
            continue
        semantics = _null_semantics(row["prod_report_filed_flag"], volume)
        records.append(
            {
                "entity_key": key,
                "production_month": month,
                "stream": stream,
                # canonical.volume is NOT NULL, so an unfiled month is carried as zero and the
                # null_semantics label is the whole of what keeps it from reading as a filed
                # zero -- the same contract nd_mpr.py states at its own promotion.
                "volume": volume if volume is not None else Decimal(0),
                "filed_volume": volume,
                "unit": unit,
                "null_semantics": semantics,
            }
        )
    return records, rejects, None


def promote_lease_cycle(
    connection: psycopg.Connection,
    manifest_id: str,
    *,
    parse_derivation_id: str,
    vintage: date,
    allowlist: set[str],
    scope_rule: ConformanceRule,
    liquids_rule: ConformanceRule,
    gas_rule: ConformanceRule,
    grain_rule: ConformanceRule,
    years: Sequence[int] | None = None,
) -> tuple[str, dict[str, int]]:
    """The filed lease volume at its native grain, promoted a calendar year at a time.

    Per year because canonical is append-only and a half-promoted vintage is a state somebody
    has to reason about: a stop lands on a year boundary with a recorded high-water month
    rather than in the middle of one.
    """
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            _STAGED_LEASE_ROWS,
            {
                "manifest_id": manifest_id,
                "years": None if years is None else [str(year) for year in years],
            },
        )
        staged = cursor.fetchall()

    records: list[dict[str, Any]] = []
    rejects: list[dict[str, Any]] = []
    excluded = 0
    keyless = 0
    for row in staged:
        made, bad, reason = _lease_records(row, allowlist=allowlist)
        if reason == "out_of_scope":
            excluded += 1
            continue
        if reason is not None:
            keyless += 1
            rejects.append({**row, "reason_code": reason})
            continue
        records.extend(made)
        rejects.extend(bad)

    with derive(
        "canonical.promote",
        output=OutputSpec(
            store="postgres",
            dataset="canonical.production_monthly",
            partition={"manifest_id": manifest_id, "entity_type": "lease", "state": "TX"},
        ),
        params={
            "reporting_level": "lease",
            "granularity": "lease_reported",
            "rows_excluded_out_of_scope": excluded,
            "years": sorted(years) if years is not None else None,
        },
        inputs=[
            InputRef(kind="derivation", ref_id=parse_derivation_id),
            InputRef(kind="manifest", ref_id=manifest_id, as_of_vintage=vintage),
        ],
        rules=[
            scope_rule.rule_id, liquids_rule.rule_id, gas_rule.rule_id, grain_rule.rule_id
        ],
    ) as context:
        context.set_rows(len(records))
        context.set_output_hash(
            hash_payload(
                {
                    "rows": sorted(
                        f"{row['entity_key']}/{row['production_month'].isoformat()}"
                        f"/{row['stream']}"
                        for row in records
                    )
                }
            )
        )

    with connection.cursor() as cursor:
        cursor.executemany(
            _INSERT_CANONICAL,
            [
                {
                    **{key: value for key, value in row.items() if key != "filed_volume"},
                    "source_id": SOURCE_ID,
                    "report_vintage": vintage,
                    "manifest_id": manifest_id,
                    "derivation_id": context.derivation_id,
                    "value_hash": hash_payload(
                        {
                            "volume": str(row["filed_volume"])
                            if row["filed_volume"] is not None
                            else None,
                            "unit": row["unit"],
                            "granularity": "lease_reported",
                            "null_semantics": row["null_semantics"],
                        }
                    ),
                }
                for row in records
            ],
        )
        appended = max(cursor.rowcount, 0)

    quarantined = 0
    for reason_code in sorted({str(reject["reason_code"]) for reject in rejects}):
        quarantined += _quarantine_lease(
            connection,
            [reject for reject in rejects if reject["reason_code"] == reason_code],
            manifest_id=manifest_id,
            reason_code=reason_code,
        )

    session = current_session()
    emit(
        connection,
        "staging.scope_excluded",
        subject_type="manifest",
        subject_id=manifest_id,
        payload={
            "rows_excluded": excluded,
            "rows_staged": len(staged),
            "scope_rule": scope_rule.rule_id,
            "lease_keys_in_scope": len(allowlist),
            "note": "the county scope is applied here because OG_LEASE_CYCLE carries no county",
        },
        correlation_id=session.correlation_id,
        occurred_at=session.clock.now(),
    )
    return context.derivation_id, {
        "rows_read": len(staged),
        "rows_built": len(records),
        "rows_appended": appended,
        "rows_excluded_out_of_scope": excluded,
        "rows_keyless": keyless,
        "rows_quarantined": quarantined,
    }


def _quarantine_lease(
    connection: psycopg.Connection,
    rows: Sequence[Mapping[str, Any]],
    *,
    manifest_id: str,
    reason_code: str,
) -> int:
    if not rows:
        return 0
    session = current_session()
    quarantine(
        connection,
        pl.DataFrame([dict(row) for row in rows], infer_schema_length=None),
        reason_code=reason_code,
        manifest_id=manifest_id,
        source_id=SOURCE_ID,
        staging_table="staging.tx_pdq_lease_cycle",
        stage="validate",
        seen_at=session.clock.now(),
        rule_id=None,
        correlation_id=session.correlation_id,
    )
    return len(rows)


def archive_well_status(
    connection: psycopg.Connection, *, raw_root: Path | str | None = None
) -> list[dict[str, Any]]:
    """Archive the two 26-month well-status files monthly, and parse neither.

    They hold the most recent 26-month reporting period against 402 months of PDQ history, so a
    window not archived is a window no regulator can give back and allocation v1's test-rate
    weighting becomes impossible. v0 weights nothing by them, which is why this fetches and
    stops.

    The vintage is the sibling the portal modified most recently, never the one with the
    expected extension. Measured 2026-09-03: the W-10 listing offered `wlf607.ebc` modified
    2021-09-24 beside a `.gz` modified 2026-08-25, and the G-10 listing offered `gse10.ebc`
    modified 2026-08-25 beside a `.gz` modified 2021-12-09. A fetcher preferring either
    extension takes a five-year-old vintage for one of the two and says nothing.
    """
    archive_rule = rule(connection, ARCHIVE_FAMILY, source_id=W10_SOURCE_ID)
    archived: list[dict[str, Any]] = []
    for source_id, spec in archive_rule.spec["archives"].items():
        with MftClient(str(spec["link"])) as mft:
            entry = _newest_sibling(mft, [str(name) for name in spec["names"]])
            fetched = fetch_raw(
                connection,
                source_id,
                entry.name,
                url=mft.url_for(entry.name),
                acquisition_method="mft_guid_resolve",
                raw_root=raw_root,
                client=mft.client,
                media_type="application/octet-stream",
                rules=[archive_rule.rule_id],
                extra_acquisition_params={
                    "sibling_preference": "newest_modified",
                    "siblings": {item.name: item.modified_label for item in mft.listing.entries},
                    "chosen": entry.name,
                },
            )
        archived.append(
            {
                "source_id": source_id,
                "source_key": entry.name,
                "manifest_id": fetched.manifest.manifest_id,
                "modified_label": entry.modified_label,
                "unchanged": bool(fetched.unchanged),
            }
        )
    return archived


def _staged_years(connection: psycopg.Connection, manifest_id: str) -> list[int]:
    """The calendar years the staged member covers, read rather than assumed."""
    with connection.cursor() as cursor:
        cursor.execute(
            "select distinct left(cycle_year_month, 4) from staging.tx_pdq_lease_cycle"
            " where manifest_id = %s and cycle_year_month ~ '^[0-9]{6}$' order by 1",
            (manifest_id,),
        )
        return [int(row[0]) for row in cursor.fetchall()]


def _newest_sibling(mft: MftClient, names: Sequence[str]) -> Any:
    """The listed sibling the portal modified last, refusing rather than guessing on a tie."""
    candidates = [entry for entry in mft.listing.entries if entry.name in set(names)]
    if not candidates:
        raise LookupError(f"none of {sorted(names)} is on the listing")
    parsed = [(_modified(entry.modified_label), entry) for entry in candidates]
    if len({stamp for stamp, _ in parsed}) != len(parsed):
        raise ArchiveFormatError(
            f"{sorted(names)}: two siblings carry one modification time, so which is the"
            " vintage is not a question this rule can answer"
        )
    return max(parsed, key=lambda item: item[0])[1]


def _modified(label: str) -> datetime:
    """The portal's own `M/D/YY h:mm:ss AM` stamp, which is what the choice turns on."""
    return datetime.strptime(label.strip(), "%m/%d/%y %I:%M:%S %p").replace(tzinfo=UTC)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch the TX RRC PDQ dump and load its crosswalk into staging and canonical."
    )
    add_dsn_argument(parser)
    parser.add_argument("--url", default=None, help="override the resolved URL (testing only)")
    parser.add_argument("--raw-root", default=None)
    parser.add_argument("--env-id", default=None, help="override the fingerprinted env id")
    parser.add_argument("--code-version", default=None)
    parser.add_argument(
        "--restage", action="store_true", help="re-parse from the stored bytes after a rule change"
    )
    parser.add_argument(
        "--stage-only",
        action="store_true",
        help="stage every member and promote no lease rows",
    )
    parser.add_argument(
        "--year",
        action="append",
        type=int,
        default=None,
        help="promote only this calendar year; repeatable",
    )
    parser.add_argument(
        "--archive-well-status",
        action="store_true",
        help="archive the 26-month W-10 and G-10 files and parse neither",
    )
    parser.add_argument(
        "--pgdata",
        default=None,
        help="assert the runbook's 40 GB relation headroom on this path before fetching",
    )
    arguments = parser.parse_args(argv)
    arguments.dsn = resolve_dsn(arguments.dsn)

    with durable_fetch_attempts(arguments.dsn), psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        with lineage_session(recorder=PostgresRecorder(connection), environment=environment):
            if arguments.archive_well_status:
                archived = archive_well_status(connection, raw_root=arguments.raw_root)
                connection.commit()
                print(json.dumps({"archived": archived}, sort_keys=True))
                return 0
            if arguments.url:
                result = load(
                    connection,
                    url=arguments.url,
                    raw_root=arguments.raw_root,
                    restage=arguments.restage,
                    pgdata=arguments.pgdata,
                    promote_years=arguments.year,
                    stage_only=arguments.stage_only,
                )
            else:
                with MftClient(PDQ_LINK) as mft:
                    result = load(
                        connection,
                        url=mft.url_for(SOURCE_KEY),
                        client=mft.client,
                        raw_root=arguments.raw_root,
                        restage=arguments.restage,
                        pgdata=arguments.pgdata,
                        promote_years=arguments.year,
                        stage_only=arguments.stage_only,
                    )
        connection.commit()
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
