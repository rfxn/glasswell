from __future__ import annotations

import importlib.util
import re
import sys
from datetime import date
from pathlib import Path

import psycopg
import pytest

from glasswell.db import migrate
from glasswell.lineage.clock import utc_today
from glasswell.seed import (
    BASIN_RULES,
    C115B_RULES,
    CO_RULES,
    FRACFOCUS_RULES,
    LAND_RULES,
    MT_RULES,
    ND_RULES,
    NM_RULES,
    NM_WELLS_GIS_RULES,
    NM_WELLS_RULES,
    PRODUCING_RULES,
    SCHEDULE_RULES,
    TX_RULES,
    TYPECURVE_RULES,
    VINTAGE_RULES,
    seed_crs,
)

MIGRATION = (
    Path(__file__).parents[2]
    / "src/glasswell/db/migrations/049_conformance_two_clock.sql"
)


def _seeded_rule_ids() -> set[str]:
    return {
        str(rule["rule_id"])
        for registry in (
            BASIN_RULES,
            CO_RULES,
            C115B_RULES,
            FRACFOCUS_RULES,
            LAND_RULES,
            MT_RULES,
            ND_RULES,
            NM_RULES,
            NM_WELLS_GIS_RULES,
            NM_WELLS_RULES,
            PRODUCING_RULES,
            SCHEDULE_RULES,
            TX_RULES,
            TYPECURVE_RULES,
            VINTAGE_RULES,
        )
        for rule in registry
    }


def test_publication_catalog_exactly_covers_the_shipped_rule_registry(db):
    with db.cursor() as cursor:
        cursor.execute(
            "select rule_id, published_vintage, evidence_tag, evidence_commit"
            " from lineage.conformance_rule_publications"
        )
        publications = {
            row[0]: {"date": row[1], "tag": row[2], "commit": row[3]}
            for row in cursor.fetchall()
        }

    assert set(publications) == _seeded_rule_ids()
    assert publications["cr_nd_status_vocab_1"] == {
        "date": date(2026, 8, 20),
        "tag": "pre-inc3-train",
        "commit": "efa39772c2877a6c4ba333fade7fa446695c1f39",
    }
    assert publications["cr_nm_wcproduction_stream_vocab_1"]["tag"] == "v0.20"
    assert publications["cr_nd_neighbor_context_1"]["tag"] == "v0.57"
    assert all(len(item["commit"]) == 40 for item in publications.values())


def test_rule_publication_is_required_matched_and_immutable(db):
    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, source_id, stage,"
            " rule_kind, rule, rationale, effective_from) values"
            " ('cr_nd_status_vocab_1', 'cr_nd_status_vocab', 'nd_mpr_xlsx', 'conform',"
            " 'vocab_map', 'r', 'r', '2026-01-01') returning published_vintage"
        )
        assert cursor.fetchone()[0] == date(2026, 8, 20)
    db.commit()

    with pytest.raises(psycopg.errors.CheckViolation, match="must be"), db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, source_id, stage,"
            " rule_kind, rule, rationale, published_vintage, effective_from) values"
            " ('cr_nd_compute_crs_1', 'cr_nd_compute_crs', 'nd_mpr_xlsx', 'conform',"
            " 'code_ref', 'r', 'r', '2026-08-21', '2026-01-01')"
        )
    db.rollback()

    with (
        pytest.raises(psycopg.errors.CheckViolation, match="no publication evidence"),
        db.cursor() as cursor,
    ):
        cursor.execute(
            "insert into lineage.conformance_rules (rule_id, rule_family, source_id, stage,"
            " rule_kind, rule, rationale, effective_from) values"
            " ('cr_unpublished_1', 'cr_unpublished', 'nd_mpr_xlsx', 'conform',"
            " 'code_ref', 'r', 'r', '2026-01-01')"
        )
    db.rollback()

    with (
        pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"),
        db.cursor() as cursor,
    ):
        cursor.execute(
            "update lineage.conformance_rules set published_vintage = '2026-08-21'"
            " where rule_id = 'cr_nd_status_vocab_1'"
        )
    db.rollback()


def test_static_lookup_clocks_are_not_nullable_and_are_indexed(db):
    tables = (
        "nd_status_map",
        "nd_stream_map",
        "nd_segment_map",
        "nd_survey_segment_map",
        "tx_status_map",
        "nm_stream_map",
        "nm_waste_type_map",
        "operator_aliases",
        "crs_registry",
    )
    with db.cursor() as cursor:
        cursor.execute(
            "select table_name from information_schema.columns"
            " where table_schema = 'lineage' and column_name = 'published_vintage'"
            " and is_nullable = 'NO' and table_name = any(%s)",
            (list(tables),),
        )
        nonnull = {row[0] for row in cursor.fetchall()}
        cursor.execute(
            "select tablename from pg_indexes where schemaname = 'lineage'"
            " and indexname like '%%publication_idx'"
        )
        indexed = {row[0] for row in cursor.fetchall()}

    assert nonnull == set(tables)
    assert set(tables) - {"operator_aliases", "crs_registry"} <= indexed
    assert "crs_registry" in {
        row[0]
        for row in db.execute(
            "select tablename from pg_indexes where schemaname = 'lineage'"
            " and indexname = 'crs_registry_two_clock_idx'"
        ).fetchall()
    }

    with db.cursor() as cursor:
        cursor.execute(
            "insert into lineage.operator_aliases"
            " (operator_raw, operator, confidence, effective_from, source_id)"
            " values ('123', 'Clocked Operator', 1.000, '1980-01-01', 'nd_mpr_xlsx')"
            " returning effective_from, published_vintage"
        )
        effective_from, published_vintage = cursor.fetchone()

    assert effective_from == date(1980, 1, 1)
    # PostgreSQL stamps this with its own current_date, so the comparison is UTC's day.
    assert published_vintage == utc_today()

    with pytest.raises(psycopg.errors.RestrictViolation, match="append_only_violation"):
        db.execute(
            "update lineage.crs_registry set note = 'rewritten' where basin = 'williston'"
        )
    db.rollback()


def test_crs_seeding_reuses_the_proven_publication_identity(db):
    seed_crs(db)
    seed_crs(db)

    rows = db.execute(
        "select basin, effective_from, published_vintage from lineage.crs_registry"
        " where basin = 'williston' order by effective_from, published_vintage"
    ).fetchall()

    assert rows == [("williston", date(2026, 1, 1), date(2026, 8, 20))]


def test_migration_replays_without_changing_publication_evidence(db):
    with db.cursor() as cursor:
        cursor.execute(
            "select md5(string_agg(rule_id || ':' || published_vintage::text || ':'"
            " || evidence_tag || ':' || evidence_commit, ',' order by rule_id))"
            " from lineage.conformance_rule_publications"
        )
        before = cursor.fetchone()[0]
        cursor.execute(MIGRATION.read_text())
        cursor.execute(
            "select md5(string_agg(rule_id || ':' || published_vintage::text || ':'"
            " || evidence_tag || ':' || evidence_commit, ',' order by rule_id))"
            " from lineage.conformance_rule_publications"
        )
        after = cursor.fetchone()[0]

    assert after == before


# The evidence a migration writes into lineage.conformance_rule_publications belongs to the
# merge train, not to this branch: the table is append-only, so a tag naming a release that has
# not run is a permanently false claim about when a rule was published. The repository's answer
# is a placeholder pair plus a release guard that refuses while it stands.
#
# Nothing below asserts that a file *contains* the placeholder. That inverts at the moment the
# integrator repoints — the correct action would turn the suite red — and it is the failure the
# sibling track shipped. What is pinned here is behaviour that holds on both sides of the
# repoint: the pair moves together, the set of writers is closed, and a placeholder named in a
# comment is not a pending repoint.
PLACEHOLDER_TAG = "UNRELEASED"
PLACEHOLDER_COMMIT = "0" * 40
TRACK_RULE_PREFIXES = ("cr_nm_wellhistory_", "cr_nm_wcproduction_pool_rollup_", "cr_nm_wells_gis_",
                       "cr_land_agg_membership_2")
TRACK_PUBLICATION_WRITER_COUNT = 3
# One rule id shares this track's prefix and is not on this track: the read-time status
# resolution, registered by its own migration on its own train with its own evidence pair. A
# prefix cannot tell two trains apart, so the later one is named rather than version-floored.
LATER_TRACK_RULE_IDS = frozenset({"cr_nm_wellhistory_status_vocab_2"})


def _migrations_dir() -> Path:
    return Path(migrate.__file__).parent / "migrations"


def _statements(text: str) -> list[str]:
    """The file's SQL statements, comment lines removed.

    Stripping comments is the whole point: the guard this mirrors was written as a bare
    substring scan, and its own header prose then matched it, so a correctly repointed file went
    on refusing forever. A migration says what its statements write, not what its sentences say.
    """
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))
    return body.split(";")


def _evidence_values(text: str) -> set[tuple[str, str]]:
    """The (tag, commit) pairs a migration actually writes, read from the quoted SQL values."""
    return set(re.findall(r"'([^']+)',\s*'([0-9a-f]{40})'", "\n".join(_statements(text))))


def _published_rule_ids(text: str) -> set[str]:
    """The rule ids a migration registers in lineage.conformance_rule_publications."""
    return {
        rule
        for statement in _statements(text)
        if "conformance_rule_publications" in statement
        for rule in re.findall(r"'(cr_[a-z0-9_]+)'", statement)
    }


def _track_publication_writers(root: Path) -> list[str]:
    """This track's publication writers, identified by the rule ids they register.

    Not by filename and not by a version floor: either is resolved by the next renumber or the
    next merge train, and both then sweep in a neighbouring track's migration silently.
    """
    return sorted(
        path.name
        for path in root.glob("*.sql")
        if (published := _published_rule_ids(path.read_text("utf-8")) - LATER_TRACK_RULE_IDS)
        and all(rule.startswith(TRACK_RULE_PREFIXES) for rule in published)
    )


def _as_repo_root(migrations: Path, layout: Path) -> Path:
    """A repository-shaped root whose migrations directory is `migrations`.

    The release guard takes a repository and globs its own migrations path, so handing it a
    bare directory silently measures the real repository instead of the fixture.
    """
    root = migrations / "_guard_root"
    link = root / layout
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.is_symlink():
        link.symlink_to(migrations, target_is_directory=True)
    return root


def _pending(root: Path) -> set[str]:
    """Migrations under `root` whose written evidence is still the placeholder pair.

    Prefers the repository's own release guard once that has merged, so this test starts
    exercising the real implementation rather than a lookalike the moment it exists.
    """
    guard = Path(__file__).resolve().parents[2] / "scripts" / "release.py"
    if guard.is_file():
        spec = importlib.util.spec_from_file_location("gw_release_guard", guard)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        blockers = getattr(module, "placeholder_evidence_blockers", None)
        if blockers is not None:
            version = module.read_version(guard.parent.parent)
            reported = " ".join(blockers(_as_repo_root(root, module.MIGRATIONS_DIR), version))
            return {path.name for path in root.glob("*.sql") if path.name in reported}
    return {
        path.name
        for path in root.glob("*.sql")
        if (PLACEHOLDER_TAG, PLACEHOLDER_COMMIT) in _evidence_values(path.read_text("utf-8"))
    }


def test_the_publication_writers_this_track_adds_are_exactly_these_three():
    """A fourth writer added later would never be seen by the guard or by the repoint."""
    root = _migrations_dir()
    writers = _track_publication_writers(root)
    registered = [
        rule
        for name in writers
        for rule in sorted(_published_rule_ids((root / name).read_text("utf-8")))
    ]

    assert len(writers) == TRACK_PUBLICATION_WRITER_COUNT, writers
    assert len(registered) == len(set(registered)), registered
    # A registration for a rule no seeder ships is a failure rather than a harmless forward
    # declaration, because the catalog is asserted to cover the shipped registry exactly.
    assert set(registered) <= _seeded_rule_ids(), sorted(set(registered) - _seeded_rule_ids())


def test_every_writer_carries_the_same_evidence_pair():
    """Repointed or not, they move together: three files half-repointed is the realistic
    mistake, and it produces two different claims about one release."""
    root = _migrations_dir()
    pairs = {
        name: _evidence_values((root / name).read_text("utf-8"))
        for name in _track_publication_writers(root)
    }

    assert pairs
    for name, values in pairs.items():
        assert len(values) == 1, (name, values)
    assert len({next(iter(values)) for values in pairs.values()}) == 1, pairs


def test_the_pair_is_all_placeholder_or_no_placeholder_never_half(db):
    """The database-level statement of the same property, over the rows that actually landed."""
    with db.cursor() as cursor:
        cursor.execute(
            "select distinct evidence_tag, evidence_commit"
            "  from lineage.conformance_rule_publications"
            " where " + " or ".join(["rule_id like %s"] * len(TRACK_RULE_PREFIXES)),
            tuple(f"{prefix}%" for prefix in TRACK_RULE_PREFIXES),
        )
        pairs = cursor.fetchall()

    assert pairs
    for tag, commit in pairs:
        assert (tag == PLACEHOLDER_TAG) == (commit == PLACEHOLDER_COMMIT), (tag, commit)
        assert commit
        assert re.fullmatch(r"[0-9a-f]{40}", commit), commit
        assert tag.strip()


def _with_evidence(text: str, tag: str, commit: str) -> str:
    """The real migration with its evidence pair set to a chosen one.

    Derived from the shipped file rather than from a synthetic blob — a synthetic fixture is
    what missed this defect on the sibling track — but independent of which pair the file
    happens to carry today, so these two tests read the same before and after the repoint.
    """
    values = _evidence_values(text)
    assert len(values) == 1, values
    current_tag, current_commit = next(iter(values))
    return text.replace(f"'{current_tag}'", f"'{tag}'").replace(
        f"'{current_commit}'", f"'{commit}'"
    )


def _a_shipped_writer() -> str:
    root = _migrations_dir()
    return (root / _track_publication_writers(root)[0]).read_text("utf-8")


def test_a_placeholder_named_only_in_a_comment_is_not_a_pending_repoint(tmp_path: Path):
    """The defect the sibling track shipped, encoded.

    A correctly repointed file whose header still *explains* the placeholder must read as clean.
    A bare substring scan matches its own prose, so the correct action goes on refusing forever
    and nothing in the repository can cut a tag.
    """
    repointed = _with_evidence(_a_shipped_writer(), "v9.99", "a" * 40)
    repointed += (
        f"\n-- Repointed from the {PLACEHOLDER_TAG} placeholder and its {PLACEHOLDER_COMMIT}\n"
        "-- commit at the merge train.\n"
    )
    (tmp_path / "099_repointed.sql").write_text(repointed, encoding="utf-8")
    # A control the guard must report, so an empty read of the fixture directory cannot pass
    # this test the way it did while _pending measured the repository instead.
    (tmp_path / "098_control.sql").write_text(
        _with_evidence(_a_shipped_writer(), PLACEHOLDER_TAG, PLACEHOLDER_COMMIT), encoding="utf-8"
    )

    assert PLACEHOLDER_TAG in repointed, "the fixture must name it in prose to be the test"
    assert _pending(tmp_path) == {"098_control.sql"}


def test_a_writer_whose_values_carry_the_placeholder_is_reported(tmp_path: Path):
    """The other direction, from the same real artifact: values decide, not prose."""
    placeheld = _with_evidence(_a_shipped_writer(), PLACEHOLDER_TAG, PLACEHOLDER_COMMIT)
    (tmp_path / "099_pending.sql").write_text(placeheld, encoding="utf-8")

    assert _pending(tmp_path) == {"099_pending.sql"}
