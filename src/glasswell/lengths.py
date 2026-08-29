"""Lateral length, in one place, under the active `cr_nd_compute_crs` rule (SB-07 §6.3).

The API, the tile mart and the ingest statistics all measure the same geometry; if each
built its own SQL they could disagree by a zone. The rule row says which method applies and
this module is the only translation of that row into SQL — the method is an allowlisted
token, never a spec string interpolated into a statement.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import psycopg

from glasswell.lineage.clock import utc_today
from glasswell.lineage.conformance import load_rules, rule_for_family
from glasswell.lineage.errors import RuleSpecError
from glasswell.lineage.models import ConformanceRule

COMPUTE_CRS_FAMILY = "cr_nd_compute_crs"
LATERALS_SOURCE_ID = "nd_gis_horizontals_line"
LENGTH_PURPOSE = "length_computation"

GEODESIC = "geodesic"
PROJECTED = "projected"
STORAGE_EPSG = 4326


@dataclass(frozen=True, slots=True)
class LengthMethod:
    rule_id: str
    method: str
    compute_epsg: int | None
    effective_from: date

    def metres_sql(self, geom: str = "geom") -> str:
        """`geom` is a code-supplied column reference; nothing here comes from the spec."""
        if self.method == GEODESIC:
            return f"ST_Length({geom}::geography)"
        return f"ST_Length(ST_Transform({geom}, {self.compute_epsg}))"

    @property
    def compute_crs(self) -> str:
        """The CRS the computation is defined on — the storage CRS when it is zone-free."""
        return f"EPSG:{self.compute_epsg if self.method == PROJECTED else STORAGE_EPSG}"


def length_method(rule: ConformanceRule) -> LengthMethod:
    method = str(rule.spec.get("length_method", PROJECTED))
    if method not in (GEODESIC, PROJECTED):
        raise RuleSpecError(f"{rule.rule_id}: length_method {method!r} is not a declared method")
    epsg = rule.spec.get("compute_epsg")
    if method == PROJECTED and not isinstance(epsg, int):
        raise RuleSpecError(f"{rule.rule_id}: a projected length needs an integer compute_epsg")
    return LengthMethod(
        rule_id=rule.rule_id,
        method=method,
        compute_epsg=int(epsg) if isinstance(epsg, int) else None,
        effective_from=rule.effective_from,
    )


def compute_crs_rule(rules: Sequence[ConformanceRule]) -> ConformanceRule:
    """The active length rule among these, found by what it is for rather than by its name.

    Each basin seeds its own instance — ND's evidence is ND laterals, TX's is TX well arcs — so
    a served length resolves to a rule about the geometry it measured. `purpose` is the
    selector because a family id is a name, and a name is what drifts between basins.
    """
    purposed = [rule for rule in rules if rule.spec.get("purpose") == LENGTH_PURPOSE]
    if not purposed:
        raise LookupError(f"no active rule declares purpose {LENGTH_PURPOSE!r}")
    if len({rule.rule_family for rule in purposed}) > 1:
        families = ", ".join(sorted({rule.rule_family for rule in purposed}))
        raise LookupError(f"{families} each claim {LENGTH_PURPOSE!r} for one source")
    return rule_for_family(purposed, purposed[0].rule_family)


_LENGTH_RULE_SOURCE = """
select length_rule_source
  from lineage.crs_registry
 where basin = %(basin)s
   and length_rule_source is not null
   and effective_from <= %(valid_at)s
   and published_vintage <= greatest(
       %(knowledge_at)s,
       coalesce((select min(baseline.published_vintage)
                   from lineage.crs_registry baseline
                  where baseline.basin = %(basin)s), %(knowledge_at)s))
 order by effective_from desc, published_vintage desc
 limit 1
"""

_SOURCE_BASELINE = """
select greatest(%(knowledge_at)s::date, coalesce(min(published_vintage), %(knowledge_at)s::date))
  from lineage.conformance_rules
 where source_id = %(source_id)s
"""


def length_rule_source(
    connection: psycopg.Connection,
    basin: str | None,
    *,
    as_of: date | None = None,
    valid_at: date | None = None,
    knowledge_at: date | None = None,
) -> str:
    """Which source's compute-CRS rule governs a basin. The registry answers, not a constant."""
    if not basin:
        return LATERALS_SOURCE_ID
    effective_cut = valid_at or as_of or utc_today()
    knowledge_cut = knowledge_at or utc_today()
    with connection.cursor() as cursor:
        cursor.execute(
            _LENGTH_RULE_SOURCE,
            {"basin": basin, "valid_at": effective_cut, "knowledge_at": knowledge_cut},
        )
        row = cursor.fetchone()
    if row is None:
        raise LookupError(f"lineage.crs_registry names no length rule source for basin {basin!r}")
    return str(row[0])


def resolve_length_method(
    connection: psycopg.Connection,
    *,
    source_id: str | None = None,
    basin: str | None = None,
    as_of: date | None = None,
    valid_at: date | None = None,
    knowledge_at: date | None = None,
) -> LengthMethod:
    """The one lookup every length path makes, so no two paths can measure differently."""
    effective_cut = valid_at or as_of or utc_today()
    knowledge_cut = knowledge_at or utc_today()
    resolved = source_id or length_rule_source(
        connection,
        basin,
        valid_at=effective_cut,
        knowledge_at=knowledge_cut,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            _SOURCE_BASELINE,
            {"source_id": resolved, "knowledge_at": knowledge_cut},
        )
        rule_knowledge_cut = cursor.fetchone()[0]
    return length_method(
        compute_crs_rule(
            load_rules(
                connection,
                source_id=resolved,
                valid_at=effective_cut,
                knowledge_at=rule_knowledge_cut,
            )
        )
    )
