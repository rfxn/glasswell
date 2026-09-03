"""Allocation v0: the lease volume canonical holds, split among the wells eligible that month.

Marts read canonical only (blueprint §3.0.1). This one reads `canonical.production_monthly` at
`entity_type = 'lease'`, `canonical.lease_membership` and `canonical.wells_latest`, and writes
the estimate — which canonical could not hold anyway: `020_production_entity_key.sql:43-46`
admits no `lease_allocated` row.

Every row says what it is. `allocation_class` distinguishes the two observed classes that
`granularity` cannot; `allocation_model_id` names the versioned artifact that computed the
number and `allocation_rule_id` the R8 decision that admitted it; `error_bounds_outcome` states
that no transferable bound has been measured and names the study that will close it. An
allocation estimate that reads as an observation is the defect this whole shape exists against.

Conservation is exact by construction, so the ledger holds volume with no eligible well to
carry it rather than a rounding term, decomposed by a closed cause vocabulary.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

from glasswell.allocation.v0 import (
    ALLOCATED_AFTER_STATUS_CHANGE,
    MODEL_ID,
    Eligible,
    allocate_lease_month,
)
from glasswell.db.dsn import add_dsn_argument, resolve_dsn
from glasswell.ingest.base import resolve_environment
from glasswell.lineage import (
    InputRef,
    OutputSpec,
    PostgresRecorder,
    current_session,
    derive,
    lineage_session,
)
from glasswell.lineage.audit import emit
from glasswell.lineage.serialization import hash_payload

ALLOCATION_RULE = "cr_tx_allocation_v0_1"
ERROR_RULE = "cr_alloc_v0_error_bounds_1"
LIQUIDS_RULE = "cr_tx_liquids_basis_1"
GAS_RULE = "cr_tx_gas_basis_1"
GRAIN_RULE = "cr_tx_production_grain_1"
SOURCE_ID = "tx_pdq_dsv"

# The mart-stream fold, restated where the allocation reads it: an oil-lease `oil` share and a
# gas-lease `condensate` share are both mart stream `liquid`, which is why the mart's key
# carries the lease and the fold cannot hide which one a share came from.
MART_STREAM = {"oil": "liquid", "condensate": "liquid", "gas": "gas"}
STREAM_UNITS = {"liquid": "bbl", "gas": "mcf"}
LIQUIDS_BASIS = "oil+condensate"

# cr_tx_production_grain_1's `completeness_lag_months`: the Commission's own sentence is that
# production records are substantially complete after about six months, so the last six months
# of every Texas chart are systematically under-filed and the rows say so.
COMPLETENESS_LAG_MONTHS = 6

# Reached only where nothing was eligible, so every code here describes that: no crosswalk row
# at all, every well completed after the month, every well plugged before it, or a mix of the
# two. `negative_correction` was in this list and nothing could write it -- a negative volume
# with an eligible well allocates -- and `all_wells_after_month` was returned for a lease whose
# wells were all plugged in 2015, which is the opposite fact (gate-tx H-14).
CAUSES = (
    "no_crosswalk_row",
    "all_wells_after_month",
    "all_wells_plugged_before_month",
    "no_eligible_well",
)

# The gas-lease discriminator, read off the lease key's own first field rather than written as
# a code: cr_tx_lease_key_1 puts OIL_GAS_CODE there because one wellbore can be completed on an
# oil lease and a gas lease, and a G row is already per well.
GAS_LEASE_PREFIX = "G-"


def jurisdiction_of(connection: psycopg.Connection, rule_id: str) -> str:
    """The jurisdiction whose serving registration names this rule.

    Read rather than written down: a jurisdiction code in a serving module is the shape
    test_add_a_state.py refuses, and it refuses it because the registry is where a jurisdiction
    is declared. If no registration names the rule, the mart has nothing to allocate for and
    says so rather than defaulting.
    """
    with connection.cursor() as cursor:
        # The registry's own knowledge cut, which is max(published_at) and not the host's
        # today: lineage/jurisdictions.py reads it that way because a registration may be
        # published for a date the deploy host has not reached, and a mart that used
        # current_date would silently allocate for nobody on the day the train lands.
        cursor.execute(
            "select r.jurisdiction_code from lineage.jurisdiction_rules r"
            "  join lineage.jurisdictions_as_of("
            "         (select max(published_at) from lineage.jurisdictions),"
            "         (select max(effective_from) from lineage.jurisdictions)) j"
            "    on (j.jurisdiction_code, j.effective_from, j.published_at)"
            "     = (r.jurisdiction_code, r.effective_from, r.published_at)"
            " where r.rule_id = %s and r.serving",
            (rule_id,),
        )
        found = cursor.fetchall()
    if len(found) != 1:
        raise ConservationError(
            f"{rule_id} is named by {len(found)} serving registrations; exactly one jurisdiction"
            " allocates under it"
        )
    return str(found[0][0])


@dataclass(frozen=True, slots=True)
class AllocationRefresh:
    derivation_id: str
    snapshot_vintage: date | None
    membership_vintage: date | None
    shares: int = 0
    ledger_rows: int = 0
    crosswalk_rows: int = 0
    lease_months: int = 0
    classes: Mapping[str, int] = field(default_factory=dict)
    causes: Mapping[str, int] = field(default_factory=dict)
    volume_allocated: Mapping[str, str] = field(default_factory=dict)
    volume_unallocated: Mapping[str, str] = field(default_factory=dict)
    share_allocated_to_retired_wells: str = "0"
    incomplete_from: date | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "derivation_id": self.derivation_id,
            "snapshot_vintage": self.snapshot_vintage.isoformat()
            if self.snapshot_vintage
            else None,
            "membership_vintage": self.membership_vintage.isoformat()
            if self.membership_vintage
            else None,
            "shares": self.shares,
            "ledger_rows": self.ledger_rows,
            "crosswalk_rows": self.crosswalk_rows,
            "lease_months": self.lease_months,
            "classes": dict(self.classes),
            "causes": dict(self.causes),
            "volume_allocated": dict(self.volume_allocated),
            "volume_unallocated": dict(self.volume_unallocated),
            "share_allocated_to_retired_wells": self.share_allocated_to_retired_wells,
            "incomplete_from": self.incomplete_from.isoformat()
            if self.incomplete_from
            else None,
        }


class ConservationError(RuntimeError):
    """V-1 failed at tolerance zero, so the refresh raises rather than publishing.

    The split is exact by construction, so a non-zero difference on an allocated lease-month is
    a defect in this module and not a residual to report. R-2 gates deploy on it.
    """


# Ordered by lease and month and read through a server-side cursor: this is the only unbounded
# relation the refresh touches, and one lease-month is resident at a time. The same reason
# marts/cumulatives.py streams its month classes rather than materialising them.
_LEASE_MONTHS = """
select entity_key as lease_key, production_month, stream, volume, null_semantics
  from canonical.production_monthly_latest
 where entity_type = 'lease' and source_id = %(source_id)s
   and null_semantics in ('reported', 'reported_zero')
 order by entity_key, production_month
"""

# Resolution is the greatest effective_from at or before the clock. v0 holds one vintage, so
# every month resolves to it -- the back-projection cr_tx_allocation_v0_1 names as its dominant
# assumption -- but the query is written for the vintage it will hold rather than for the one
# it holds today.
_MEMBERSHIP = """
select m.lease_key, m.api10, w.completion_date, w.plug_date, w.status_canonical
  from canonical.lease_membership m
  join canonical.wells_latest w on w.api10 = m.api10
 where m.jurisdiction_code = %(jurisdiction)s
   and m.effective_from = (
       select max(effective_from) from canonical.lease_membership
        where jurisdiction_code = m.jurisdiction_code and lease_key = m.lease_key
          and effective_from <= %(as_of)s)
"""

_MEMBERSHIP_VINTAGE = """
select max(effective_from) from canonical.lease_membership
 where jurisdiction_code = %(jurisdiction)s
"""

_SNAPSHOT_VINTAGE = """
select max(report_vintage) from canonical.production_monthly
 where entity_type = 'lease' and source_id = %(source_id)s
"""

_LEASE_DERIVATIONS = """
select distinct derivation_id from canonical.production_monthly
 where entity_type = 'lease' and source_id = %(source_id)s
"""

# V-2a as the spec puts it: "wells in one crosswalk and not the other, and wells assigned to
# different lease keys, as counts, shares and a district breakdown". The two crosswalks are
# retained unmerged (cr_tx_ewa_role_1) and this is the only measurement of identity-mapping
# error the system has. It reports; it does not gate.
#
# Written in this pass rather than by a job of its own: it is a measurement over the same
# membership the split reads, at the same vintage, and a second job would be a second clock
# over one input.
_CROSSWALK_DERIVATIONS = """
select distinct derivation_id from canonical.lease_membership
 where jurisdiction_code = %(jurisdiction)s and link_role = 'canonical_crosswalk'
   and effective_from = (select max(effective_from) from canonical.lease_membership
                          where jurisdiction_code = %(jurisdiction)s
                            and link_role = 'canonical_crosswalk')
union
select distinct derivation_id from canonical.well_lease_links
 where link_role = 'validator_a'
   and effective_from = (select max(effective_from) from canonical.well_lease_links
                          where link_role = 'validator_a')
"""

# Both sides, counted before anything is written: with one crosswalk loaded and the other not,
# every well is "in one and not the other" and the block would publish 100 percent
# disagreement -- a measured residual over an input nobody loaded. An absent side is an absent
# measurement, and the validators block already says so with its own reason.
_CROSSWALK_SIDES = """
select
    (select count(*) from canonical.lease_membership
      where jurisdiction_code = %(jurisdiction)s and link_role = 'canonical_crosswalk') as pdq,
    (select count(*) from canonical.well_lease_links
      where link_role = 'validator_a') as validator
"""

_INSERT_CROSSWALK = """
with pdq as (
    select api10, array_agg(distinct lease_key order by lease_key) as keys,
           min(split_part(lease_key, '-', 2)) as district_no
      from canonical.lease_membership
     where jurisdiction_code = %(jurisdiction)s and link_role = 'canonical_crosswalk'
       and effective_from = (select max(effective_from) from canonical.lease_membership
                              where jurisdiction_code = %(jurisdiction)s
                                and link_role = 'canonical_crosswalk')
     group by api10
),
validator as (
    select api10, array_agg(distinct lease_key order by lease_key) as keys,
           min(district_no) as district_no
      from canonical.well_lease_links
     where link_role = 'validator_a'
       and effective_from = (select max(effective_from) from canonical.well_lease_links
                              where link_role = 'validator_a')
     group by api10
),
joined as (
    select coalesce(v.district_no, p.district_no) as district_no,
           case
               when v.keys is null then 'only_in_pdq'
               when p.keys is null then 'only_in_validator'
               when p.keys <> v.keys then 'different_lease_key'
               else 'agree'
           end as disagreement_kind
      from pdq p full outer join validator v on v.api10 = p.api10
),
totals as (
    select district_no, count(*)::numeric as wells from joined group by district_no
)
insert into marts.tx_crosswalk_residual
    (district_no, disagreement_kind, well_count, share, snapshot_vintage, derivation_id)
select j.district_no, j.disagreement_kind, count(*),
       round(count(*)::numeric / t.wells, 4), %(snapshot_vintage)s, %(derivation_id)s
  from joined j join totals t on t.district_no = j.district_no
 where j.disagreement_kind <> 'agree' and j.district_no is not null
 group by j.district_no, j.disagreement_kind, t.wells
"""

_INSERT_SHARE = """
insert into marts.tx_allocated_production (
    api10, lease_key, production_month, stream, volume, unit, basis, allocation_class,
    granularity, allocation_model_id, allocation_rule_id, eligible_wells, membership_vintage,
    incomplete_window, error_bounds_outcome, error_rule_id, lease_derivation_id,
    snapshot_vintage, derivation_id)
values (%(api10)s, %(lease_key)s, %(production_month)s, %(stream)s, %(volume)s, %(unit)s,
        %(basis)s, %(allocation_class)s, %(granularity)s, %(allocation_model_id)s,
        %(allocation_rule_id)s, %(eligible_wells)s, %(membership_vintage)s,
        %(incomplete_window)s, 'not_measured', %(error_rule_id)s, %(lease_derivation_id)s,
        %(snapshot_vintage)s, %(derivation_id)s)
"""

_INSERT_LEDGER = """
insert into marts.tx_allocation_ledger
    (lease_key, production_month, stream, lease_volume, cause, snapshot_vintage, derivation_id)
values (%(lease_key)s, %(production_month)s, %(stream)s, %(lease_volume)s, %(cause)s,
        %(snapshot_vintage)s, %(derivation_id)s)
"""


def eligibility(
    row: Mapping[str, object], month: date
) -> Eligible:
    """`cr_tx_allocation_v0_1`'s predicate, as one decision per well-month.

    A filed plug date is a dated fact and bounds; a `plugged` status with no date is a
    today-snapshot and does not, so the well stays eligible and its months are labelled. The
    two are different decisions and v0 makes only the first, which is what stops a card serving
    "plugged" beside a chart running to the present with nothing reconciling them.
    """
    completion = row["completion_date"]
    plug = row["plug_date"]
    eligible = True
    if completion is not None and completion > month:
        eligible = False
    if plug is not None and month > plug:
        eligible = False
    return Eligible(
        api10=str(row["api10"]),
        eligible=eligible,
        plugged_without_date=plug is None and row["status_canonical"] == "plugged",
    )


def _membership(
    connection: psycopg.Connection, as_of: date, jurisdiction: str
) -> dict[str, list[dict[str, object]]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_MEMBERSHIP, {"jurisdiction": jurisdiction, "as_of": as_of})
        rows = cursor.fetchall()
    by_lease: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_lease.setdefault(str(row["lease_key"]), []).append(row)
    return by_lease


def _scalar(connection: psycopg.Connection, statement: str, params: Mapping[str, object]):
    with connection.cursor() as cursor:
        cursor.execute(statement, dict(params))
        found = cursor.fetchone()
    return found[0] if found else None


def _incomplete_from(latest: date | None) -> date | None:
    """The first month inside the completeness lag, which the series shades and warns about."""
    if latest is None:
        return None
    months = latest.year * 12 + latest.month - 1 - (COMPLETENESS_LAG_MONTHS - 1)
    return date(months // 12, months % 12 + 1, 1)


def _lease_month_rows(connection: psycopg.Connection) -> Iterator[dict[str, object]]:
    with connection.cursor(name="tx_lease_months", row_factory=dict_row) as cursor:
        cursor.itersize = 20_000
        cursor.execute(_LEASE_MONTHS, {"source_id": SOURCE_ID})
        yield from cursor


def _cause(
    candidates: Sequence[Eligible], wells: Sequence[Mapping[str, object]], month: date
) -> str:
    """Why this lease-month reached no well, read off the rows rather than off a default."""
    if not candidates:
        return "no_crosswalk_row"
    after = sum(
        1
        for well in wells
        if well["completion_date"] is not None and well["completion_date"] > month
    )
    plugged = sum(
        1 for well in wells if well["plug_date"] is not None and month > well["plug_date"]
    )
    if after == len(wells):
        return "all_wells_after_month"
    if plugged == len(wells):
        return "all_wells_plugged_before_month"
    return "no_eligible_well"


def build(
    connection: psycopg.Connection,
    *,
    membership: Mapping[str, Sequence[Mapping[str, object]]],
    membership_vintage: date | None,
    snapshot_vintage: date | None,
    lease_derivation_id: str,
    incomplete_from: date | None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    """Every share and every unallocated lease-month, with conservation checked as it goes."""
    shares: list[dict[str, object]] = []
    ledger: list[dict[str, object]] = []
    classes: dict[str, int] = {}
    causes: dict[str, int] = dict.fromkeys(CAUSES, 0)
    allocated: dict[str, Decimal] = {"liquid": Decimal(0), "gas": Decimal(0)}
    unallocated: dict[str, Decimal] = {"liquid": Decimal(0), "gas": Decimal(0)}
    retired: Decimal = Decimal(0)
    lease_months = 0

    for row in _lease_month_rows(connection):
        lease_key = str(row["lease_key"])
        month = row["production_month"]
        stream = MART_STREAM[str(row["stream"])]
        volume = Decimal(row["volume"])
        lease_months += 1
        gas_lease = lease_key.startswith(GAS_LEASE_PREFIX)

        wells = list(membership.get(lease_key, ()))
        candidates = [eligibility(well, month) for well in wells]
        allocated_shares = allocate_lease_month(volume, candidates, gas_lease=gas_lease)
        if not allocated_shares:
            cause = _cause(candidates, wells, month)
            causes[cause] += 1
            unallocated[stream] += volume
            ledger.append(
                {
                    "lease_key": lease_key,
                    "production_month": month,
                    "stream": stream,
                    "lease_volume": volume,
                    "cause": cause,
                    "snapshot_vintage": snapshot_vintage,
                }
            )
            continue

        total = sum(share.volume for share in allocated_shares)
        if total != volume:
            raise ConservationError(
                f"{lease_key} {month} {stream}: shares sum to {total} and the lease filed"
                f" {volume}; the split is exact by construction, so this is a defect"
            )
        allocated[stream] += volume
        for share in allocated_shares:
            classes[share.allocation_class] = classes.get(share.allocation_class, 0) + 1
            if share.allocation_class == ALLOCATED_AFTER_STATUS_CHANGE:
                retired += abs(share.volume)
            shares.append(
                {
                    "api10": share.api10,
                    "lease_key": lease_key,
                    "production_month": month,
                    "stream": stream,
                    "volume": share.volume,
                    "unit": STREAM_UNITS[stream],
                    "basis": LIQUIDS_BASIS if stream == "liquid" else None,
                    "allocation_class": share.allocation_class,
                    "granularity": share.granularity,
                    "allocation_model_id": MODEL_ID,
                    "allocation_rule_id": ALLOCATION_RULE,
                    "eligible_wells": share.eligible_wells,
                    "membership_vintage": membership_vintage,
                    "incomplete_window": incomplete_from is not None and month >= incomplete_from,
                    "error_rule_id": ERROR_RULE,
                    "lease_derivation_id": lease_derivation_id,
                    "snapshot_vintage": snapshot_vintage,
                }
            )

    total_allocated = sum(abs(value) for value in allocated.values())
    measured = {
        "classes": classes,
        "causes": causes,
        "volume_allocated": {stream: str(value) for stream, value in allocated.items()},
        "volume_unallocated": {stream: str(value) for stream, value in unallocated.items()},
        # The one eligibility error term with no date behind it, bounded rather than open.
        "share_allocated_to_retired_wells": str(
            (retired / total_allocated).quantize(Decimal("0.0001"))
            if total_allocated
            else Decimal(0)
        ),
        "lease_months": lease_months,
    }
    return shares, ledger, measured


def refresh_tx_allocation(connection: psycopg.Connection) -> AllocationRefresh:
    """Rebuild the allocated mart and its conservation ledger under one derivation."""
    jurisdiction = jurisdiction_of(connection, ALLOCATION_RULE)
    membership_vintage = _scalar(
        connection, _MEMBERSHIP_VINTAGE, {"jurisdiction": jurisdiction}
    )
    snapshot_vintage = _scalar(connection, _SNAPSHOT_VINTAGE, {"source_id": SOURCE_ID})
    with connection.cursor() as cursor:
        cursor.execute(_LEASE_DERIVATIONS, {"source_id": SOURCE_ID})
        lease_derivations = sorted(row[0] for row in cursor.fetchall())
        cursor.execute(
            "select max(production_month) from canonical.production_monthly_latest"
            " where entity_type = 'lease' and source_id = %(source_id)s",
            {"source_id": SOURCE_ID},
        )
        found = cursor.fetchone()
        latest_month = found[0] if found else None
    with connection.cursor() as cursor:
        cursor.execute(_CROSSWALK_DERIVATIONS, {"jurisdiction": jurisdiction})
        crosswalk_derivations = sorted(row[0] for row in cursor.fetchall())
    if not lease_derivations:
        raise ConservationError(
            "no Texas lease production is promoted, so there is nothing to allocate"
        )

    incomplete_from = _incomplete_from(latest_month)
    membership = (
        _membership(connection, membership_vintage, jurisdiction) if membership_vintage else {}
    )
    shares, ledger, measured = build(
        connection,
        membership=membership,
        membership_vintage=membership_vintage,
        snapshot_vintage=snapshot_vintage,
        lease_derivation_id=lease_derivations[-1],
        incomplete_from=incomplete_from,
    )

    fingerprint = hash_payload(
        {
            "shares": [json.dumps(row, sort_keys=True, default=str) for row in shares],
            "ledger": [json.dumps(row, sort_keys=True, default=str) for row in ledger],
        }
    )
    with derive(
        "alloc.apply",
        output=OutputSpec(
            store="postgres",
            dataset="marts.tx_allocated_production",
            partition={"jurisdiction": jurisdiction},
            schema_version="1",
        ),
        params={
            "allocation_model_id": MODEL_ID,
            "membership_vintage": membership_vintage.isoformat()
            if membership_vintage
            else None,
            "snapshot_vintage": snapshot_vintage.isoformat() if snapshot_vintage else None,
            "liquids_basis": LIQUIDS_BASIS,
            "completeness_lag_months": COMPLETENESS_LAG_MONTHS,
            "incomplete_from": incomplete_from.isoformat() if incomplete_from else None,
            "error_bounds_outcome": "not_measured",
            **measured,
        },
        inputs=[
            InputRef(kind="derivation", ref_id=derivation_id)
            for derivation_id in (*lease_derivations, *crosswalk_derivations)
        ],
        rules=[ALLOCATION_RULE, LIQUIDS_RULE, GAS_RULE, GRAIN_RULE, ERROR_RULE],
    ) as context:
        context.set_rows(len(shares) + len(ledger))
        context.set_output_hash(fingerprint)

    with connection.cursor() as cursor:
        cursor.execute("delete from marts.tx_allocated_production")
        cursor.execute("delete from marts.tx_allocation_ledger")
        cursor.execute("delete from marts.tx_crosswalk_residual")
        cursor.executemany(
            _INSERT_SHARE,
            [{**row, "derivation_id": context.derivation_id} for row in shares],
        )
        cursor.executemany(
            _INSERT_LEDGER,
            [{**row, "derivation_id": context.derivation_id} for row in ledger],
        )
        cursor.execute(_CROSSWALK_SIDES, {"jurisdiction": jurisdiction})
        pdq_rows, validator_rows = cursor.fetchone()
        crosswalk_rows = 0
        if pdq_rows and validator_rows:
            cursor.execute(
                _INSERT_CROSSWALK,
                {
                    "jurisdiction": jurisdiction,
                    "snapshot_vintage": snapshot_vintage,
                    "derivation_id": context.derivation_id,
                },
            )
            crosswalk_rows = cursor.rowcount

    session = current_session()
    emit(
        connection,
        "mart.refreshed",
        subject_type="derivation",
        subject_id=context.derivation_id,
        payload={
            "shares": len(shares),
            "ledger_rows": len(ledger),
            "crosswalk_rows": crosswalk_rows,
            **measured,
        },
        correlation_id=session.correlation_id,
        occurred_at=session.clock.now(),
    )
    return AllocationRefresh(
        derivation_id=context.derivation_id,
        snapshot_vintage=snapshot_vintage,
        membership_vintage=membership_vintage,
        shares=len(shares),
        ledger_rows=len(ledger),
        crosswalk_rows=crosswalk_rows,
        lease_months=int(measured["lease_months"]),
        classes=measured["classes"],
        causes=measured["causes"],
        volume_allocated=measured["volume_allocated"],
        volume_unallocated=measured["volume_unallocated"],
        share_allocated_to_retired_wells=str(measured["share_allocated_to_retired_wells"]),
        incomplete_from=incomplete_from,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refresh the Texas allocated-production mart and its conservation ledger."
    )
    add_dsn_argument(parser)
    parser.add_argument("--env-id", default=None, help="override the fingerprinted env id")
    parser.add_argument("--code-version", default=None)
    arguments = parser.parse_args(argv)
    arguments.dsn = resolve_dsn(arguments.dsn)

    with psycopg.connect(arguments.dsn) as connection:
        environment = resolve_environment(
            connection, env_id=arguments.env_id, code_version=arguments.code_version
        )
        with lineage_session(recorder=PostgresRecorder(connection), environment=environment):
            report = refresh_tx_allocation(connection)
        connection.commit()
        print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
