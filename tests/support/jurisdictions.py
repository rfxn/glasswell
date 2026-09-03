"""The registry decisions as `seed/jurisdictions.py` declares them, keyed by API state code.

Tests that used to read a per-state dict out of a router read this instead. It is not a second
copy: `tests/contract/test_jurisdiction_parity.py` holds the declaration to the rows the
migration wrote and to what `jurisdictions_as_of` resolves, so a test reading it is reading the
registry one indirection away — and gets there without a connection.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import timedelta

import psycopg
from psycopg.rows import dict_row

from glasswell.lineage.clock import utc_today
from glasswell.lineage.jurisdictions import clear_jurisdiction_cache
from glasswell.seed.jurisdictions import (
    JURISDICTION_RULES,
    JURISDICTIONS,
    SUPERSEDED_RULE_SETS,
    rule_parameters,
)

_PREFIX_OF = {str(row["jurisdiction_code"]): str(row["identity_prefix"]) for row in JURISDICTIONS}
_BY_PREFIX = {str(row["identity_prefix"]): row for row in JURISDICTIONS}


def registration(prefix: str) -> dict[str, object] | None:
    return _BY_PREFIX.get(prefix)


def serving_rules() -> list[dict[str, object]]:
    """The rule rows in force: the restatement, with any supersession over the top.

    A supersession is a third family of registration row, and a helper that reads two of them
    answers for a registry that no longer exists -- which is how a gate went on asserting that
    Texas registers no liquids policy after the day it registered one (gate-tx H-4).
    """
    rows = [
        row
        for row in (rule_parameters(rule) for rule in JURISDICTION_RULES)
        if str(row["jurisdiction_code"]) not in SUPERSEDED_RULE_SETS
    ]
    for code, rules in sorted(SUPERSEDED_RULE_SETS.items()):
        rows += [
            row
            for row in (rule_parameters(rule) for rule in rules)
            if str(row["jurisdiction_code"]) == code
        ]
    return rows


def declared_rule(prefix: str, decision: str) -> str | None:
    """The serving rule id a jurisdiction registers for one decision, or None."""
    return next(
        (
            str(row["rule_id"])
            for row in serving_rules()
            if _PREFIX_OF.get(str(row["jurisdiction_code"])) == prefix
            and row["decision"] == decision
            and row["serving"]
        ),
        None,
    )


def declared_rule_ids(decision: str) -> set[str]:
    """Every serving rule id registered for one decision, across all jurisdictions."""
    return {
        str(row["rule_id"])
        for row in serving_rules()
        if row["decision"] == decision and row["serving"]
    }


def prefixes_registering(decision: str) -> set[str]:
    return {
        _PREFIX_OF[str(row["jurisdiction_code"])]
        for row in serving_rules()
        if row["decision"] == decision and row["serving"]
    }


_COLUMNS = (
    "jurisdiction_code", "effective_from", "published_at", "evidence_tag", "evidence_commit",
    "name", "regulator_name", "regulator_url", "identity_scheme", "identity_is_unique",
    "identity_prefix", "identity_pattern", "source_ids", "liquids_basis",
    "wells_tile_layer_id", "map_colour", "neighbors_available", "land_grid_state",
    "land_grid_scope", "status_dataset_detail", "rationale", "wells_layer_id",
    "wells_style_layer_ids", "wells_draw_order", "wells_default_on", "wells_snapshot_key",
    "wells_subtitle_template", "legend_note",
)


def restate(
    connection: psycopg.Connection,
    code: str,
    *,
    rules: Mapping[str, str] | None = None,
    drop: Sequence[str] = (),
    **changes: object,
) -> None:
    """Append a restatement of one registration and re-append its rule rows.

    The same `effective_from` with a later `published_at`, which is the only append that moves
    a served value on the same day the founding row was written. The rule rows travel with it
    because a row published at T2 states what was known at T2 (§2.3), so this is also the shape
    that proves gate (b) is not vacuous.
    """
    today = utc_today()
    with connection.cursor(row_factory=dict_row) as cursor:
        # The knowledge cut `load_jurisdictions` uses, not the host clock: a restatement
        # published ahead of today is what the serving path resolves, so restating the row
        # today's date resolves to would append underneath it and change nothing.
        cursor.execute("select max(published_at) as knowledge from lineage.jurisdictions")
        knowledge = cursor.fetchone()["knowledge"]
        cursor.execute(
            "select * from lineage.jurisdictions_as_of(%s, %s) where jurisdiction_code = %s",
            (knowledge, today, code),
        )
        current = cursor.fetchone()
        assert current is not None, f"{code} resolves to no registration"
        cursor.execute(
            "select decision, rule_id, serving, note from lineage.jurisdiction_rules"
            " where jurisdiction_code = %s and effective_from = %s and published_at = %s",
            (code, current["effective_from"], current["published_at"]),
        )
        carried = cursor.fetchall()

    published_at = current["published_at"] + timedelta(days=1)
    row = {**{column: current[column] for column in _COLUMNS}, "published_at": published_at}
    row.update(changes)
    columns = ", ".join(_COLUMNS)
    binds = ", ".join(f"%({column})s" for column in _COLUMNS)
    overrides = dict(rules or {})
    appended = [
        {**rule, "rule_id": overrides.pop(rule["decision"], rule["rule_id"])}
        for rule in carried
        if rule["decision"] not in drop
    ]
    appended += [
        {"decision": decision, "rule_id": rule_id, "serving": True, "note": None}
        for decision, rule_id in overrides.items()
    ]
    with connection.cursor() as cursor:
        cursor.execute(f"insert into lineage.jurisdictions ({columns}) values ({binds})", row)
        cursor.executemany(
            "insert into lineage.jurisdiction_rules (jurisdiction_code, effective_from,"
            " published_at, decision, rule_id, serving, note)"
            " values (%(jurisdiction_code)s, %(effective_from)s, %(published_at)s,"
            " %(decision)s, %(rule_id)s, %(serving)s, %(note)s)",
            [
                {
                    **rule,
                    "jurisdiction_code": code,
                    "effective_from": current["effective_from"],
                    "published_at": published_at,
                }
                for rule in appended
            ],
        )
    clear_jurisdiction_cache()
