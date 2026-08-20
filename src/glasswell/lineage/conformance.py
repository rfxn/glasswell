"""Table-driven conformance rules (SB-07 §6). Promotion code holds no mapping literals."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation

import polars as pl
import psycopg
from psycopg.rows import dict_row

from glasswell.lineage.errors import RuleSpecError, UnknownRuleKind
from glasswell.lineage.models import ConformanceRule

RULE_KINDS: tuple[str, ...] = (
    "unit_conform",
    "vocab_map",
    "alias_join",
    "datum_transform",
    "key_composite",
    "parse_directive",
    "validity_filter",
    "code_ref",
)

_ROUNDING_MODES = {
    "half_up": ROUND_HALF_UP,
    "half_even": ROUND_HALF_EVEN,
    "down": ROUND_DOWN,
}

_UNMATCHED_ACTIONS = ("quarantine", "passthrough")
_MARKER = "__glasswell_rule_target"


@dataclass(frozen=True, slots=True)
class QuarantineBatch:
    reason_code: str
    rule_id: str
    frame: pl.DataFrame


@dataclass(frozen=True, slots=True)
class RuleApplication:
    frame: pl.DataFrame
    applied_rule_ids: list[str]
    quarantined: list[QuarantineBatch]


Executor = Callable[[pl.DataFrame, ConformanceRule], tuple[pl.DataFrame, list[QuarantineBatch]]]


def _require(condition: object, rule: ConformanceRule, message: str) -> None:
    if not condition:
        raise RuleSpecError(f"{rule.rule_id} ({rule.rule_kind}): {message}")


def _decimal(rule: ConformanceRule, field: str, raw: object) -> Decimal:
    _require(
        isinstance(raw, str),
        rule,
        f"{field} must be a decimal string, not {type(raw).__name__}",
    )
    try:
        return Decimal(str(raw))
    except InvalidOperation as exc:
        raise RuleSpecError(f"{rule.rule_id}: {field} is not a decimal: {raw!r}") from exc


def _unit_conform(
    frame: pl.DataFrame, rule: ConformanceRule
) -> tuple[pl.DataFrame, list[QuarantineBatch]]:
    factor = _decimal(rule, "factor", rule.spec.get("factor"))
    mode_name = rule.spec.get("rounding")
    _require(mode_name in _ROUNDING_MODES, rule, f"rounding {mode_name!r} is not a declared mode")
    scale = rule.spec.get("scale")
    _require(isinstance(scale, int), rule, "scale must be an integer")
    _require(rule.applies_to_fields, rule, "applies_to_fields is empty")

    mode = _ROUNDING_MODES[str(mode_name)]
    exponent = Decimal(1).scaleb(-int(str(scale)))

    def convert(value: Decimal | None) -> Decimal | None:
        return None if value is None else (value * factor).quantize(exponent, rounding=mode)

    for field in rule.applies_to_fields:
        _require(field in frame.columns, rule, f"{field} is not a column of the frame")
        # Decimal.quantize is the only route with a declarable rounding mode (§4.4).
        frame = frame.with_columns(
            pl.col(field)
            .map_elements(convert, return_dtype=pl.Decimal(38, int(str(scale))))
            .cast(frame.schema[field])
            .alias(field)
        )
    return frame, []


def _split_on_marker(
    frame: pl.DataFrame, rule: ConformanceRule, target_col: str, action: str, reason_code: str
) -> tuple[pl.DataFrame, list[QuarantineBatch]]:
    _require(action in _UNMATCHED_ACTIONS, rule, f"unmapped_action {action!r} is not supported")
    _require(target_col not in frame.columns, rule, f"{target_col} already exists on the frame")
    resolved = frame.rename({_MARKER: target_col})
    if action == "passthrough":
        return resolved, []
    unresolved = resolved.filter(pl.col(target_col).is_null()).drop(target_col)
    kept = resolved.filter(pl.col(target_col).is_not_null())
    if unresolved.is_empty():
        return kept, []
    return kept, [QuarantineBatch(reason_code=reason_code, rule_id=rule.rule_id, frame=unresolved)]


def _vocab_map(
    frame: pl.DataFrame, rule: ConformanceRule
) -> tuple[pl.DataFrame, list[QuarantineBatch]]:
    key_col = str(rule.spec.get("key_col", ""))
    value_col = str(rule.spec.get("value_col", ""))
    _require(key_col and value_col, rule, "key_col and value_col are required")
    _require(key_col in frame.columns, rule, f"{key_col} is not a column of the frame")
    _require(rule.lookup, rule, f"mapping table {rule.spec.get('mapping_table')!r} loaded no rows")

    mapping = {str(row[key_col]): str(row[value_col]) for row in rule.lookup}
    _require(
        len(mapping) == len(rule.lookup),
        rule,
        f"mapping table {rule.spec.get('mapping_table')!r} has duplicate keys",
    )
    marked = frame.with_columns(
        pl.col(key_col).replace_strict(mapping, default=None, return_dtype=pl.String).alias(_MARKER)
    )
    action = str(rule.spec.get("unmapped_action", "quarantine"))
    reason = str(rule.spec.get("reason_code", "unknown_vocab"))
    return _split_on_marker(marked, rule, value_col, action, reason)


def _alias_join(
    frame: pl.DataFrame, rule: ConformanceRule
) -> tuple[pl.DataFrame, list[QuarantineBatch]]:
    key_cols = list(rule.spec.get("key_cols", []))
    target_col = str(rule.spec.get("target_col", ""))
    _require(key_cols and target_col, rule, "key_cols and target_col are required")
    for key_col in key_cols:
        _require(key_col in frame.columns, rule, f"{key_col} is not a column of the frame")
    minimum = _decimal(rule, "min_confidence", rule.spec.get("min_confidence"))

    confident = [
        row for row in rule.lookup if Decimal(str(row.get("confidence", "1"))) >= minimum
    ]
    keys_seen = {tuple(str(row[c]) for c in key_cols) for row in confident}
    _require(
        len(keys_seen) == len(confident),
        rule,
        f"alias table {rule.spec.get('alias_table')!r} has duplicate keys above min_confidence",
    )

    aliases = pl.DataFrame(
        [
            {**{c: str(row[c]) for c in key_cols}, _MARKER: str(row[target_col])}
            for row in confident
        ],
        schema={**dict.fromkeys(key_cols, pl.String), _MARKER: pl.String},
    )
    marked = frame.join(aliases, on=key_cols, how="left", maintain_order="left")
    action = str(rule.spec.get("unmatched_action", "quarantine"))
    reason = str(rule.spec.get("reason_code", "alias_unresolved"))
    return _split_on_marker(marked, rule, target_col, action, reason)


def _unimplemented(kind: str) -> Executor:
    def executor(
        frame: pl.DataFrame, rule: ConformanceRule
    ) -> tuple[pl.DataFrame, list[QuarantineBatch]]:
        raise NotImplementedError(
            f"conformance rule kind {kind!r} has no executor yet (rule {rule.rule_id})"
        )

    return executor


_EXECUTORS: dict[str, Executor] = {
    "unit_conform": _unit_conform,
    "vocab_map": _vocab_map,
    "alias_join": _alias_join,
    "datum_transform": _unimplemented("datum_transform"),
    "key_composite": _unimplemented("key_composite"),
    "parse_directive": _unimplemented("parse_directive"),
    "validity_filter": _unimplemented("validity_filter"),
    "code_ref": _unimplemented("code_ref"),
}


def executor_for(kind: str) -> Executor:
    try:
        return _EXECUTORS[kind]
    except KeyError:
        raise UnknownRuleKind(
            f"{kind!r} is not a conformance rule kind; expected one of {', '.join(RULE_KINDS)}"
        ) from None


def apply_rules(frame: pl.DataFrame, rules: Sequence[ConformanceRule]) -> RuleApplication:
    """Execute loaded rules in registry order. Rejected rows leave the frame with a reason."""
    applied: list[str] = []
    quarantined: list[QuarantineBatch] = []
    for rule in rules:
        frame, batches = executor_for(rule.rule_kind)(frame, rule)
        applied.append(rule.rule_id)
        quarantined.extend(batches)
    return RuleApplication(frame=frame, applied_rule_ids=applied, quarantined=quarantined)


_LOAD_RULES = """
select rule_id, rule_family, supersedes_rule_id, source_id, stage, applies_to_fields,
       rule_kind, spec, rule, rationale, evidence_url, evidence_sha256, effective_from,
       effective_to, code_ref, code_ref_sha256, created_by_event_id
  from lineage.conformance_rules
 where source_id = %(source_id)s
   and (%(stage)s::text is null or stage = %(stage)s)
   and effective_from <= %(as_of)s
   and (effective_to is null or effective_to > %(as_of)s)
 order by rule_id
"""

_LOOKUP_TABLES = {"mapping_table", "alias_table"}


def load_rules(
    connection: psycopg.Connection,
    *,
    source_id: str,
    stage: str | None = None,
    as_of: date | None = None,
) -> list[ConformanceRule]:
    """Read the registry and materialize the lookup rows each rule's spec names."""
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            _LOAD_RULES,
            {"source_id": source_id, "stage": stage, "as_of": as_of or date.today()},
        )
        rows = cursor.fetchall()
    return [_hydrate(connection, ConformanceRule(**row)) for row in rows]


def _hydrate(connection: psycopg.Connection, rule: ConformanceRule) -> ConformanceRule:
    for key in _LOOKUP_TABLES:
        table = rule.spec.get(key)
        if not table:
            continue
        with connection.cursor(row_factory=dict_row) as cursor:
            # Table name comes from a registry row, so it is validated as an identifier.
            cursor.execute(f"select * from lineage.{_identifier(table)}")
            rule = rule.model_copy(update={"lookup": cursor.fetchall()})
    return rule


def _identifier(name: object) -> str:
    text = str(name)
    if not text.replace("_", "").isalnum() or not text[0].isalpha():
        raise RuleSpecError(f"{text!r} is not a valid registry table name")
    return text


def apply_registry_rules(
    connection: psycopg.Connection,
    frame: pl.DataFrame,
    *,
    source_id: str,
    stage: str,
    as_of: date | None = None,
) -> RuleApplication:
    """SB-07 §11 apply_rules(): load from the registry, then execute."""
    return apply_rules(frame, load_rules(connection, source_id=source_id, stage=stage, as_of=as_of))
