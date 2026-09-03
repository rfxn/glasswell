"""The jurisdiction registry as the serving path reads it: rows, resolved at two clocks.

`lineage.jurisdictions_as_of(knowledge_as_of, valid_as_of)` decides which registration answers;
this module turns its rows into the two lookups every consumer needs -- by jurisdiction code,
and by the API-10 prefix the wire has always carried -- and refuses rather than defaulting when
the registry cannot answer at all.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date

import psycopg
from psycopg.rows import dict_row

from glasswell.lineage.clock import utc_today
from glasswell.lineage.errors import LineageError

# The registry decisions this package names. Spelled here rather than in each consumer: three
# modules read `neighbors_scope` and a fourth spelling is how a decision name drifts.
NEIGHBORS_SCOPE = "neighbors_scope"


class JurisdictionRegistryError(LineageError):
    """R8: the definition is rows, so a missing registry is a refusal, never a default.

    An unregistered *code* still yields a null rule, which is an answer. An unloaded or
    ambiguous *registry* is a service fault, and the API serves service_degraded for it.
    """


@dataclass(frozen=True, slots=True)
class JurisdictionRule:
    decision: str
    rule_id: str
    serving: bool
    note: str | None


@dataclass(frozen=True, slots=True)
class Jurisdiction:
    jurisdiction_code: str
    level: str
    effective_from: date
    published_at: date
    evidence_tag: str
    evidence_commit: str
    name: str
    regulator_name: str
    regulator_url: str
    identity_scheme: str
    identity_is_unique: bool
    identity_prefix: str | None
    identity_pattern: str | None
    source_ids: tuple[str, ...]
    liquids_basis: str | None
    wells_tile_layer_id: str | None
    map_colour: str | None
    neighbors_available: bool
    explorer_default: bool
    land_grid_state: bool
    land_grid_scope: bool
    status_dataset_detail: str | None
    rationale: str
    # 075's presentation columns. Read here rather than only through the generated client
    # module, so a legend note or a subtitle can change without a rebuild and the two copies
    # can be gated against each other.
    wells_layer_id: str | None
    wells_style_layer_ids: tuple[str, ...] | None
    wells_draw_order: int | None
    wells_default_on: bool | None
    wells_snapshot_key: str | None
    wells_subtitle_template: str | None
    legend_note: str | None
    rules: tuple[JurisdictionRule, ...] = field(default=())

    def rule(self, decision: str) -> str | None:
        """The serving rule id for one decision, or None where none is registered."""
        return next(
            (rule.rule_id for rule in self.rules if rule.decision == decision and rule.serving),
            None,
        )

    def decisions(self) -> frozenset[str]:
        return frozenset(rule.decision for rule in self.rules if rule.serving)


@dataclass(frozen=True, slots=True)
class JurisdictionRegistry:
    knowledge_as_of: date
    valid_as_of: date
    by_code: Mapping[str, Jurisdiction]
    by_prefix: Mapping[str, Jurisdiction]

    def __iter__(self) -> Iterator[Jurisdiction]:
        return iter(sorted(self.by_code.values(), key=lambda row: row.jurisdiction_code))

    def __len__(self) -> int:
        return len(self.by_code)

    def at_prefix(self, identity_prefix: str | None) -> Jurisdiction | None:
        """The registration an API-10 prefix resolves to. Unregistered is None, not a guess."""
        return self.by_prefix.get(identity_prefix or "")

    def rule_for(self, identity_prefix: str | None, decision: str) -> str | None:
        row = self.at_prefix(identity_prefix)
        return row.rule(decision) if row is not None else None

    def name_for(self, identity_prefix: str | None) -> str | None:
        row = self.at_prefix(identity_prefix)
        return row.name if row is not None else None


_RESOLVED = """
select j.*, c.level, coalesce(r.rules, '[]'::jsonb) as rules
  from lineage.jurisdictions_as_of(%(knowledge_as_of)s, %(valid_as_of)s) j
  join lineage.jurisdiction_codes c on c.jurisdiction_code = j.jurisdiction_code
  left join lateral (
      select jsonb_agg(jsonb_build_object(
                 'decision', d.decision, 'rule_id', d.rule_id,
                 'serving', d.serving, 'note', d.note)
             order by d.decision, d.rule_id) as rules
        from lineage.jurisdiction_rules d
       where d.jurisdiction_code = j.jurisdiction_code
         and d.effective_from = j.effective_from
         and d.published_at = j.published_at) r on true
 order by j.jurisdiction_code
"""

_LATEST_PUBLISHED = "select max(published_at) from lineage.jurisdictions"

# The instants at which the answer can change. Both clocks gate `jurisdictions_as_of`, so the
# resolved registration set is identical for every date between one instant and the next, and
# a cache keyed on the instants holds one entry per registry state rather than one per date a
# caller can type. gate-v076 H-3: `?as_of=` fed the caller's date straight into the key.
_CLOCK_INSTANTS = """
select max(published_at) filter (where published_at <= %(knowledge_as_of)s) as knowledge_instant,
       max(effective_from) filter (where effective_from <= %(valid_as_of)s) as valid_instant
  from lineage.jurisdictions
"""

_ROW_FIELDS = tuple(
    name
    for name in Jurisdiction.__dataclass_fields__
    if name not in ("source_ids", "wells_style_layer_ids", "rules")
)

# Keyed on the resolved clock pair R-2 names, and on the database the rows came from: the suite
# gives every test its own, and a cache that could not tell them apart would serve one another's.
# Rows rather than a built registry, because the registry carries the clocks it was *asked* for
# and two callers can ask differently and resolve to the same instants.
_CACHE: dict[tuple[str, str, str, date, date], tuple[Jurisdiction, ...]] = {}


def clear_jurisdiction_cache() -> None:
    _CACHE.clear()


def _instance(connection: psycopg.Connection) -> tuple[str, str, str]:
    info = connection.info
    return (info.host or "", str(info.port or ""), info.dbname or "")


def jurisdiction_from_row(row: Mapping[str, object]) -> Jurisdiction:
    """One `jurisdictions_as_of` row, with its rules already aggregated as JSON."""
    style_layers = row["wells_style_layer_ids"]
    return Jurisdiction(
        **{name: row[name] for name in _ROW_FIELDS},  # type: ignore[arg-type]
        source_ids=tuple(row["source_ids"]),  # type: ignore[arg-type]
        wells_style_layer_ids=tuple(style_layers) if style_layers is not None else None,
        rules=tuple(
            JurisdictionRule(
                decision=rule["decision"],
                rule_id=rule["rule_id"],
                serving=rule["serving"],
                note=rule["note"],
            )
            for rule in row["rules"]  # type: ignore[union-attr]
        ),
    )


def build_registry(
    resolved: list[Jurisdiction], knowledge_as_of: date, valid_as_of: date
) -> JurisdictionRegistry:
    by_prefix: dict[str, Jurisdiction] = {}
    for row in resolved:
        if row.identity_prefix is None:
            continue
        collision = by_prefix.get(row.identity_prefix)
        # The partial unique index can only see a collision at one (effective_from,
        # published_at); two registrations a day apart both resolve and it never fires (N-3).
        if collision is not None:
            raise JurisdictionRegistryError(
                f"identity_prefix {row.identity_prefix} resolves to both"
                f" {collision.jurisdiction_code} and {row.jurisdiction_code} at knowledge"
                f" {knowledge_as_of.isoformat()} / valid {valid_as_of.isoformat()}"
            )
        by_prefix[row.identity_prefix] = row
    return JurisdictionRegistry(
        knowledge_as_of=knowledge_as_of,
        valid_as_of=valid_as_of,
        by_code={row.jurisdiction_code: row for row in resolved},
        by_prefix=by_prefix,
    )


def load_jurisdictions(
    connection: psycopg.Connection, as_of: date | None = None
) -> JurisdictionRegistry:
    """The registrations serving at `as_of`, or at the latest published vintage and today.

    Cached per clock pair and per database. `scripts/deploy.sh` restarts the API after
    `seed_all`, so a registration appended by a deploy is read by the process that follows it.
    """
    with connection.cursor() as cursor:
        cursor.execute(_LATEST_PUBLISHED)
        latest = cursor.fetchone()[0]
    knowledge_as_of = as_of or latest
    valid_as_of = as_of or utc_today()
    if knowledge_as_of is None:
        raise JurisdictionRegistryError(
            "the jurisdiction registry holds no registration: nothing has been published"
        )

    # Resolved before the key is built, never after: this is what bounds the cache to the
    # registry's own history instead of to the set of dates a caller can send.
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            _CLOCK_INSTANTS,
            {"knowledge_as_of": knowledge_as_of, "valid_as_of": valid_as_of},
        )
        instants = cursor.fetchone()
    resolved_knowledge = instants["knowledge_instant"]
    resolved_valid = instants["valid_instant"]
    if resolved_knowledge is None or resolved_valid is None:
        raise JurisdictionRegistryError(
            "the jurisdiction registry resolves no registration at knowledge"
            f" {knowledge_as_of.isoformat()} / valid {valid_as_of.isoformat()}"
        )

    key = (*_instance(connection), resolved_knowledge, resolved_valid)
    rows = _CACHE.get(key)
    if rows is None:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                _RESOLVED,
                {"knowledge_as_of": resolved_knowledge, "valid_as_of": resolved_valid},
            )
            fetched = cursor.fetchall()
        if not fetched:
            raise JurisdictionRegistryError(
                "the jurisdiction registry resolves no registration at knowledge"
                f" {knowledge_as_of.isoformat()} / valid {valid_as_of.isoformat()}"
            )
        rows = tuple(jurisdiction_from_row(row) for row in fetched)
        _CACHE[key] = rows

    # The registry reports the clocks it was asked for, not the instants those resolved to, so
    # the served `as_of` and the cursor minted from it are byte-identical to before.
    return build_registry(list(rows), knowledge_as_of, valid_as_of)
