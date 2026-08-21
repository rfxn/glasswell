"""Table-driven conformance rules (SB-07 §6). Promotion code holds no mapping literals."""

from __future__ import annotations

import operator as _operator
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from functools import lru_cache
from typing import Any

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
    # Rows each rule touched. A rule cited with a row count it never touched is an overclaim
    # in the ledger the product sells as its evidence (fp-audit D4).
    applied_rows: dict[str, int]


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


def _declared_width(width: object, rule: ConformanceRule, column: str, key: str) -> int:
    _require(
        isinstance(width, int) and not isinstance(width, bool) and width > 0,
        rule,
        f"{key}[{column}] must be a positive integer, not {width!r}",
    )
    return int(str(width))


def _key_composite(
    frame: pl.DataFrame, rule: ConformanceRule
) -> tuple[pl.DataFrame, list[QuarantineBatch]]:
    """The S-E entity key, assembled from declared columns (SB-01 §2.10, §4.1).

    NM reports at well-completion x pool and TX's `LEASE_NO` is unique within district only, so
    neither key is derivable from one column. A partial key is a wrong key: a row missing any
    component leaves under the declared reason rather than keying on what happens to be there.

    **Padding normalises a width; it never invents identity.** Every segment is judged on the
    value the source shipped, before any padding, against three declared bounds:

    * empty or null — missing, as it always was;
    * longer than `pad[col]` — refused, never truncated. `zfill` silently overbuilds (a
      six-digit component under a five-wide pad yields an eleven-character API-10) and SQL's
      `lpad` silently truncates onto a different real well. Both are wrong (D1-P3);
    * shorter than `min_width[col]` — refused, never padded up. The RRC ships county plot
      points whose API field holds the three-digit county code alone, and `'003'.zfill(8)`
      builds `4200000003`: a syntactically perfect API-10 for a well that does not exist,
      which then reaches the map. `min_width` is what separates a lease number whose leading
      zeros the source dropped from a record that is not the thing at all.

    `min_width` defaults to 1, so a rule that declares no minimum keeps the old behaviour for
    everything except overbuilding, which is refused everywhere.
    """
    source_cols = [str(column) for column in rule.spec.get("source_cols") or ()]
    target_col = str(rule.spec.get("target_col", ""))
    _require(source_cols, rule, "source_cols is required and names at least one column")
    _require(target_col, rule, "target_col is required")
    separator = rule.spec.get("separator", "")
    _require(isinstance(separator, str), rule, "separator must be a string")
    pad = rule.spec.get("pad") or {}
    _require(isinstance(pad, Mapping), rule, "pad must map a column name to a width")
    minimums = rule.spec.get("min_width") or {}
    _require(isinstance(minimums, Mapping), rule, "min_width must map a column name to a width")
    _require(
        set(minimums) <= set(pad),
        rule,
        f"min_width names {sorted(set(minimums) - set(pad))}, which pad does not",
    )
    for column in source_cols:
        _require(column in frame.columns, rule, f"{column} is not a column of the frame")

    parts = []
    for column in source_cols:
        shipped = pl.col(column).cast(pl.String)
        length = shipped.str.len_chars()
        # An empty component is missing, not a key that happens to render as `a::b`.
        usable = shipped.is_not_null() & (length > 0)
        value = shipped
        if column in pad:
            width = _declared_width(pad[column], rule, column, "pad")
            floor = _declared_width(minimums.get(column, 1), rule, column, "min_width")
            _require(
                floor <= width,
                rule,
                f"min_width[{column}] {floor} exceeds pad[{column}] {width}",
            )
            usable = usable & (length <= width) & (length >= floor)
            value = shipped.str.zfill(width)
        parts.append(pl.when(usable).then(value).otherwise(pl.lit(None, dtype=pl.String)))
    marked = frame.with_columns(
        pl.concat_str(parts, separator=separator, ignore_nulls=False).alias(_MARKER)
    )
    action = str(rule.spec.get("on_missing", "quarantine"))
    reason = str(rule.spec.get("reason_code", "key_incomplete"))
    return _split_on_marker(marked, rule, target_col, action, reason)


PREDICATE_NODE_TYPES: tuple[str, ...] = (
    "and",
    "or",
    "not",
    "cmp",
    "in",
    "between",
    "is_null",
)

_CMP_OPERATORS: dict[str, Callable[[pl.Expr, pl.Expr], pl.Expr]] = {
    "==": _operator.eq,
    "!=": _operator.ne,
    "<": _operator.lt,
    "<=": _operator.le,
    ">": _operator.gt,
    ">=": _operator.ge,
}

_COLUMN_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")
_LITERAL_TYPES = (str, int, float, bool, type(None))
_ROW_INDEX = "__glasswell_row_index"


def _predicate_error(message: str) -> RuleSpecError:
    return RuleSpecError(f"predicate_ast: {message}")


def _is_list(payload: object) -> bool:
    return isinstance(payload, (list, tuple))


def _leaf(node: object) -> pl.Expr:
    if not isinstance(node, Mapping) or len(node) != 1:
        raise _predicate_error(f"{node!r} is not a column or literal leaf")
    key, value = next(iter(node.items()))
    if key == "col":
        if not isinstance(value, str) or not _COLUMN_RE.match(value):
            raise _predicate_error(f"{value!r} is not a column name")
        return pl.col(value)
    if key == "lit":
        if not isinstance(value, _LITERAL_TYPES):
            raise _predicate_error(f"{value!r} is not a scalar literal")
        return pl.lit(value)
    raise _predicate_error(f"{key!r} is not a leaf type; expected col or lit")


def _junction(payload: object, symbol: str) -> pl.Expr:
    if not _is_list(payload) or not payload:
        raise _predicate_error(f"{symbol} takes a non-empty list of nodes")
    expression = _compile_predicate(payload[0])
    for node in payload[1:]:
        operand = _compile_predicate(node)
        expression = expression & operand if symbol == "and" else expression | operand
    return expression


def _cmp(payload: object) -> pl.Expr:
    if not _is_list(payload) or len(payload) != 3:
        raise _predicate_error("cmp takes [left, operator, right]")
    left, symbol, right = payload
    if symbol not in _CMP_OPERATORS:
        raise _predicate_error(f"{symbol!r} is not an allowlisted comparison operator")
    return _CMP_OPERATORS[str(symbol)](_leaf(left), _leaf(right))


def _in(payload: object) -> pl.Expr:
    if not _is_list(payload) or len(payload) != 2:
        raise _predicate_error("in takes [value, [option, ...]]")
    value, options = payload
    if not _is_list(options) or not options:
        raise _predicate_error("in takes a non-empty option list")
    if any(not isinstance(option, _LITERAL_TYPES) for option in options):
        raise _predicate_error("in options must be scalar literals")
    return _leaf(value).is_in(list(options))


def _between(payload: object) -> pl.Expr:
    if not _is_list(payload) or len(payload) != 3:
        raise _predicate_error("between takes [value, low, high]")
    value, low, high = payload
    return _leaf(value).is_between(_leaf(low), _leaf(high), closed="both")


_PREDICATE_COMPILERS: dict[str, Callable[[Any], pl.Expr]] = {
    "and": lambda payload: _junction(payload, "and"),
    "or": lambda payload: _junction(payload, "or"),
    "not": lambda payload: _compile_predicate(payload).not_(),
    "cmp": _cmp,
    "in": _in,
    "between": _between,
    "is_null": lambda payload: _leaf(payload).is_null(),
}


def _compile_predicate(node: object) -> pl.Expr:
    """SB-07 §6.1: an allowlisted AST, never eval — rules are data and data is reachable."""
    if not isinstance(node, Mapping) or len(node) != 1:
        raise _predicate_error(f"{node!r} is not a single-key predicate node")
    node_type, payload = next(iter(node.items()))
    if node_type not in PREDICATE_NODE_TYPES:
        raise _predicate_error(
            f"{node_type!r} is not an allowlisted node type; "
            f"expected one of {', '.join(PREDICATE_NODE_TYPES)}"
        )
    return _PREDICATE_COMPILERS[str(node_type)](payload)


def _validity_filter(
    frame: pl.DataFrame, rule: ConformanceRule
) -> tuple[pl.DataFrame, list[QuarantineBatch]]:
    predicate = rule.spec.get("predicate_ast")
    _require(predicate is not None, rule, "predicate_ast is required")
    action = str(rule.spec.get("on_fail", "quarantine"))
    _require(action == "quarantine", rule, f"on_fail {action!r} is not supported yet")
    reason = rule.spec.get("reason_code")
    _require(isinstance(reason, str) and reason, rule, "reason_code is required")

    # A row the predicate cannot judge is not a valid row; it is quarantined, never assumed.
    keep = _compile_predicate(predicate).fill_null(False)
    kept = frame.filter(keep)
    rejected = frame.filter(~keep)
    if rejected.is_empty():
        return kept, []
    return kept, [QuarantineBatch(reason_code=str(reason), rule_id=rule.rule_id, frame=rejected)]


def _parse_directive(
    frame: pl.DataFrame, rule: ConformanceRule
) -> tuple[pl.DataFrame, list[QuarantineBatch]]:
    """Validation only: this kind configures a reader, which consumes the spec in ingest."""
    declared = [str(column) for column in rule.spec.get("expected_columns") or ()]
    if not declared:
        declared = [field for field in rule.applies_to_fields if field != "all"]
    if not declared:
        return frame, []

    policy = str(rule.spec.get("header_policy", "contains"))
    missing = [column for column in declared if column not in frame.columns]
    extra = [c for c in frame.columns if c not in declared] if policy == "declared" else []
    if not missing and not extra:
        return frame, []
    # The header failed, not any one row: nothing parsed under it can be trusted.
    return frame.clear(), [
        QuarantineBatch(reason_code="schema_mismatch", rule_id=rule.rule_id, frame=frame)
    ]


@lru_cache(maxsize=64)
def _transformer(source_epsg: int, target_epsg: int):
    # Imported lazily: pyproj loads the PROJ database, and most spine callers never project.
    from pyproj import Transformer

    return Transformer.from_crs(f"EPSG:{source_epsg}", f"EPSG:{target_epsg}", always_xy=True)


def _coordinate_columns(frame: pl.DataFrame, rule: ConformanceRule) -> tuple[str, str]:
    detect = rule.spec.get("detect") or {}
    _require(isinstance(detect, Mapping), rule, "detect must be an object")
    x = detect.get("x_col") or detect.get("lon_col") or rule.spec.get("x_col")
    y = detect.get("y_col") or detect.get("lat_col") or rule.spec.get("y_col")
    # The ND seeds keep detect for the .prj signature and name the pair in applies_to_fields.
    if not y:
        y = next((f for f in rule.applies_to_fields if f.lower().startswith("lat")), None)
    if not x:
        x = next((f for f in rule.applies_to_fields if f.lower().startswith("lon")), None)
    _require(x and y, rule, "detect must name x_col and y_col, or applies_to_fields a lat/lon pair")
    for column in (str(x), str(y)):
        _require(column in frame.columns, rule, f"{column} is not a column of the frame")
    return str(x), str(y)


def _datum_transform(
    frame: pl.DataFrame, rule: ConformanceRule
) -> tuple[pl.DataFrame, list[QuarantineBatch]]:
    x_col, y_col = _coordinate_columns(frame, rule)
    target = rule.spec.get("target_epsg")
    _require(isinstance(target, int), rule, "target_epsg is required")
    detect = rule.spec.get("detect") or {}
    epsg_col = detect.get("epsg_col")
    source = rule.spec.get("source_epsg")
    _require(
        isinstance(source, int) or epsg_col,
        rule,
        "source_epsg or detect.epsg_col is required; a datum is never assumed",
    )
    if epsg_col:
        _require(epsg_col in frame.columns, rule, f"{epsg_col} is not a column of the frame")

    work = frame.with_row_index(_ROW_INDEX)
    placeable = pl.col(x_col).is_not_null() & pl.col(y_col).is_not_null()
    if epsg_col:
        placeable = placeable & pl.col(str(epsg_col)).is_not_null()
    placed = work.filter(placeable)
    unplaceable = work.filter(~placeable)

    groups = placed.partition_by(str(epsg_col)) if epsg_col else [placed]
    transformed: list[pl.DataFrame] = []
    for group in groups:
        if group.is_empty():
            continue
        code = int(group[str(epsg_col)][0]) if epsg_col else int(str(source))
        xs, ys = _transformer(code, int(str(target))).transform(
            group[x_col].to_list(), group[y_col].to_list()
        )
        transformed.append(group.with_columns(pl.Series(x_col, xs), pl.Series(y_col, ys)))

    placed = pl.concat(transformed) if transformed else placed
    finite = pl.col(x_col).is_finite() & pl.col(y_col).is_finite()
    diverged = placed.filter(~finite)
    kept = placed.filter(finite).sort(_ROW_INDEX).drop(_ROW_INDEX)
    rejected = pl.concat([unplaceable, diverged]).sort(_ROW_INDEX).drop(_ROW_INDEX)
    if rejected.is_empty():
        return kept, []
    return kept, [
        QuarantineBatch(reason_code="datum_undetermined", rule_id=rule.rule_id, frame=rejected)
    ]


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
    "datum_transform": _datum_transform,
    "key_composite": _key_composite,
    "parse_directive": _parse_directive,
    "validity_filter": _validity_filter,
    "code_ref": _unimplemented("code_ref"),
}


def executor_for(kind: str) -> Executor:
    try:
        return _EXECUTORS[kind]
    except KeyError:
        raise UnknownRuleKind(
            f"{kind!r} is not a conformance rule kind; expected one of {', '.join(RULE_KINDS)}"
        ) from None


def active_rules(rules: Sequence[ConformanceRule]) -> list[ConformanceRule]:
    """R8 supersession: rows are immutable, so a successor row is what retires its ancestor."""
    superseded = {rule.supersedes_rule_id for rule in rules if rule.supersedes_rule_id}
    return [rule for rule in rules if rule.rule_id not in superseded]


def rule_for_family(rules: Sequence[ConformanceRule], family: str) -> ConformanceRule:
    """Pin a family, never a version: a supersession changes the id and must not be missed."""
    for rule in rules:
        if rule.rule_family == family:
            return rule
    raise LookupError(f"no active rule in family {family}")


def apply_rules(frame: pl.DataFrame, rules: Sequence[ConformanceRule]) -> RuleApplication:
    """Execute loaded rules in registry order. Rejected rows leave the frame with a reason."""
    applied: list[str] = []
    touched: dict[str, int] = {}
    quarantined: list[QuarantineBatch] = []
    for rule in rules:
        handed = frame
        frame, batches = executor_for(rule.rule_kind)(frame, rule)
        applied.append(rule.rule_id)
        # An executor that hands back the frame it was given and rejects nothing — a
        # parse_directive validating a header — read no rows and stamps none.
        touched[rule.rule_id] = 0 if frame is handed and not batches else handed.height
        quarantined.extend(batches)
    return RuleApplication(
        frame=frame, applied_rule_ids=applied, quarantined=quarantined, applied_rows=touched
    )


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
    loaded = active_rules([ConformanceRule(**row) for row in rows])
    return [_hydrate(connection, rule) for rule in loaded]


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


_LEASE_REPORTING = """
select rule_id, rule, spec ->> 'reporting_level' as reporting_level
  from lineage.conformance_rules
 where spec ->> 'state_code' = %s
   and spec ->> 'reporting_level' = 'lease'
   and (spec -> 'allocation_required')::boolean
   and (effective_to is null or effective_to > current_date)
 order by effective_from desc
 limit 1
"""


def lease_reporting_rule(
    connection: psycopg.Connection, state_code: str | None
) -> dict[str, str] | None:
    """The rule saying a jurisdiction reports production at the lease, or None.

    R8 again: which states need allocation is a registry fact with a date and a rationale, not
    a list of state codes in a serving path. A well in such a state has no observed well-level
    series, and the honest answer on its card is that one is pending — not that none was
    reported (DIR-3).
    """
    if not state_code:
        return None
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(_LEASE_REPORTING, (state_code,))
        row = cursor.fetchone()
    return dict(row) if row else None
