"""Lateral length, in one place, under the active `cr_nd_compute_crs` rule (SB-07 §6.3).

The API, the tile mart and the ingest statistics all measure the same geometry; if each
built its own SQL they could disagree by a zone. The rule row says which method applies and
this module is the only translation of that row into SQL — the method is an allowlisted
token, never a spec string interpolated into a statement.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import psycopg

from glasswell.lineage.conformance import load_rules, rule_for_family
from glasswell.lineage.errors import RuleSpecError
from glasswell.lineage.models import ConformanceRule

COMPUTE_CRS_FAMILY = "cr_nd_compute_crs"
LATERALS_SOURCE_ID = "nd_gis_horizontals_line"

GEODESIC = "geodesic"
PROJECTED = "projected"
STORAGE_EPSG = 4326


@dataclass(frozen=True, slots=True)
class LengthMethod:
    rule_id: str
    method: str
    compute_epsg: int | None

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
    )


def compute_crs_rule(rules: Sequence[ConformanceRule]) -> ConformanceRule:
    return rule_for_family(rules, COMPUTE_CRS_FAMILY)


def resolve_length_method(connection: psycopg.Connection) -> LengthMethod:
    """The one lookup every length path makes, so no two paths can measure differently."""
    return length_method(compute_crs_rule(load_rules(connection, source_id=LATERALS_SOURCE_ID)))
