"""M-3: the reason a row was rejected is a fact, and the ledger has to carry the true one.

Migration 007's CHECK omitted two codes the seeded rules name, so `nd_mpr` degraded every
one of them to `unknown_vocab` — 98.7 % of the live ledger under the label "the ingest does
not understand its own source file". Migration 011 admits the codes and relabels the rows
whose `rule_id` already proves what the reason was.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import psycopg
import pytest
from psycopg.types.json import Jsonb

from glasswell.db.migrate import discover_migrations, migrate
from glasswell.ingest.nd_mpr import UNREGISTERED_REASON, _reason_vocabulary
from glasswell.seed import (
    BASIN_RULES,
    C115B_RULES,
    FRACFOCUS_RULES,
    LAND_RULES,
    MT_RULES,
    ND_RULES,
    NM_RULES,
    NM_WELLS_GIS_RULES,
    NM_WELLS_RULES,
    PRODUCING_RULES,
    TX_RULES,
    TYPECURVE_RULES,
    seed_conformance_nd,
    seed_sources,
)
from tests.conftest import FIXTURE_ENV_ID
from tests.support.seed import seed_manifest

RELABEL_VERSION = 11
RELABELLED = {
    "cr_nd_stream_vocab_1": "stream_not_promoted",
    "cr_nd_status_vocab_1": "unknown_status",
}
SEEN_AT = datetime(2026, 8, 1, 5, 2, 11, tzinfo=UTC)

_INSERT_QUARANTINE = (
    "insert into lineage.quarantine_rows (quarantine_id, row_fingerprint, source_id,"
    " staging_table, stage, reason_code, rule_id, row_payload, first_seen_at,"
    " first_seen_manifest_id, last_seen_at, last_seen_manifest_id)"
    " values (%s, %s, 'nd_mpr_xlsx', 'staging.nd_mpr_oil', 'conform', %s, %s, %s, %s, %s, %s, %s)"
)


# Every seeded set, not just North Dakota's. A migration that rebuilds the CHECK from its own
# branch's baseline drops whatever another track added, and the single-state form of this guard
# could not see it: 063 silently removed New Mexico's two coordinate codes.
ALL_RULE_SETS = (
    BASIN_RULES,
    C115B_RULES,
    FRACFOCUS_RULES,
    LAND_RULES,
    MT_RULES,
    ND_RULES,
    NM_RULES,
    NM_WELLS_GIS_RULES,
    NM_WELLS_RULES,
    PRODUCING_RULES,
    TX_RULES,
    TYPECURVE_RULES,
)


def _transport_reasons() -> set[str]:
    """Fetch-failure reasons, which land on a raw.fetch_failed audit event and never on a
    quarantine row. Read off the exception classes so the exclusion cannot drift from them."""
    from glasswell.lineage import ftp

    return {
        value.glasswell_reason
        for value in vars(ftp).values()
        if isinstance(value, type)
        and issubclass(value, ftp.FtpError)
        and hasattr(value, "glasswell_reason")
    }


def _seeded_reason_codes(rule_sets=ALL_RULE_SETS) -> set[str]:
    transport = _transport_reasons()
    return {
        str(rule["spec"]["reason_code"])
        for rules in rule_sets
        for rule in rules
        if "reason_code" in rule["spec"]  # type: ignore[operator]
    } - transport


def _staged_migrations(tmp_path, up_to: int):
    directory = tmp_path / f"migrations_{up_to:03d}"
    directory.mkdir()
    for migration in discover_migrations():
        if migration.version <= up_to:
            (directory / migration.path.name).write_bytes(migration.path.read_bytes())
    return directory


def _rows(connection: psycopg.Connection, sql: str, *parameters: object) -> list[tuple]:
    with connection.cursor() as cursor:
        cursor.execute(sql, parameters or None)
        return cursor.fetchall()


def test_every_seeded_rule_names_a_reason_code_the_ledger_can_store(db):
    """A rule whose reason code the CHECK refuses is either degraded or a crash on ingest."""
    missing = _seeded_reason_codes() - _reason_vocabulary(db)
    assert not missing, (
        f"the quarantine CHECK admits no {sorted(missing)} — a migration rebuilding the"
        " enumeration from its own branch's baseline dropped another track's codes"
    )


def test_the_degradation_fallback_survives_as_a_safety_net(db):
    """Widening the CHECK does not remove the guard: a future unregistered code still lands."""
    assert UNREGISTERED_REASON in _reason_vocabulary(db)


@pytest.fixture
def mislabelled(empty_db, tmp_path) -> psycopg.Connection:
    """The ledger as migration 010 left it: true reasons flattened onto `unknown_vocab`."""
    migrate(empty_db, _staged_migrations(tmp_path, RELABEL_VERSION - 1))
    empty_db.commit()
    # Not seed_all: this database stops at migration 10, and the registries later
    # migrations create are not in it. The ledger under test is ND's.
    seed_sources(empty_db)
    seed_conformance_nd(empty_db)
    with empty_db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.environments (env_id, python_version, threads)"
            " values (%s, '3.12.10', 1)",
            (FIXTURE_ENV_ID,),
        )
    empty_db.commit()
    manifest = seed_manifest(empty_db, sha256="c" * 64)
    with empty_db.cursor() as cursor:
        for ordinal, rule_id in enumerate((*RELABELLED, "cr_nd_units_1", None)):
            cursor.execute(
                _INSERT_QUARANTINE,
                (
                    f"qr_relabel{ordinal:04d}",
                    f"fp_relabel_{ordinal:04d}",
                    "unknown_vocab",
                    rule_id,
                    Jsonb({"stream_raw": "GasSold"}),
                    SEEN_AT,
                    manifest,
                    SEEN_AT,
                    manifest,
                ),
            )
    empty_db.commit()
    return empty_db


def test_the_relabel_corrects_exactly_the_rows_whose_rule_proves_the_reason(
    mislabelled, tmp_path
):
    migrate(mislabelled, _staged_migrations(tmp_path, RELABEL_VERSION))
    mislabelled.commit()

    assert dict(
        _rows(
            mislabelled,
            "select rule_id, reason_code from lineage.quarantine_rows"
            " where rule_id = any(%s) order by rule_id",
            list(RELABELLED),
        )
    ) == RELABELLED


def test_the_relabel_leaves_a_genuinely_unknown_row_alone(mislabelled, tmp_path):
    """A row whose rule names no other code is not evidence of anything else."""
    migrate(mislabelled, _staged_migrations(tmp_path, RELABEL_VERSION))
    mislabelled.commit()

    assert _rows(
        mislabelled,
        "select count(*) from lineage.quarantine_rows"
        " where reason_code = 'unknown_vocab' and (rule_id is null or rule_id = 'cr_nd_units_1')",
    ) == [(2,)]


def test_the_relabel_is_recorded_as_an_audit_event_per_rule(mislabelled, tmp_path):
    """A correction to the ledger is itself a fact about the ledger (SB-07 §5)."""
    migrate(mislabelled, _staged_migrations(tmp_path, RELABEL_VERSION))
    mislabelled.commit()

    recorded = _rows(
        mislabelled,
        "select subject_id, payload from lineage.audit_events"
        " where event_type = 'quarantine.relabelled' order by subject_id",
    )

    assert [subject for subject, _ in recorded] == sorted(RELABELLED)
    for subject, payload in recorded:
        assert payload["from"] == "unknown_vocab"
        assert payload["to"] == RELABELLED[subject]
        assert payload["rows"] == 1


def test_the_reason_enumeration_only_ever_grows_across_migrations():
    """Each rebuild of the CHECK must be a superset of the one before it.

    The constraint cannot be appended to, so every migration that adds a code restates the whole
    list — and a track branching before another's codes land restates a list without them. 063
    did exactly that, dropping New Mexico's two coordinate refusals, and every database-backed
    test in the repository errored at fixture setup. Reason codes are emitted from module
    literals as well as rule specs, so a guard reading the registry alone cannot see it; this
    reads the migrations themselves.
    """
    rebuild = re.compile(
        r"add constraint quarantine_rows_reason_code_check\s*check\s*\(reason_code in \((.*?)\)\)",
        re.DOTALL,
    )
    previous: set[str] = set()
    previous_name = "(none)"
    checked = 0
    for migration in discover_migrations():
        text = migration.path.read_text(encoding="utf-8")
        match = rebuild.search(text)
        if match is None:
            continue
        codes = set(re.findall(r"'([a-z_]+)'", match.group(1)))
        lost = previous - codes
        assert not lost, (
            f"{migration.path.name} drops {sorted(lost)} admitted by {previous_name} — restate"
            " the full enumeration including every code already landed, then add your own"
        )
        previous, previous_name = codes, migration.path.name
        checked += 1
    assert checked >= 2, "no migration pair rebuilt the enumeration; the pattern moved"
