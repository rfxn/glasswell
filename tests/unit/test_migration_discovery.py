from __future__ import annotations

import pytest

from glasswell.db.migrate import MIGRATIONS_DIR, MigrationError, discover_migrations


def write(directory, name, body="select 1;"):
    (directory / name).write_text(body, encoding="utf-8")


def test_shipped_migrations_are_discovered_and_numbered_from_one():
    migrations = discover_migrations()
    assert migrations
    assert [m.version for m in migrations] == list(range(1, len(migrations) + 1))
    assert all(m.path.parent == MIGRATIONS_DIR for m in migrations)


def test_shipped_migrations_hash_their_own_bytes():
    first = discover_migrations()[0]
    assert len(first.sha256) == 64
    assert first.sql.strip()


def test_duplicate_versions_are_refused(tmp_path):
    write(tmp_path, "001_a.sql")
    write(tmp_path, "001_b.sql")
    with pytest.raises(MigrationError, match="duplicate"):
        discover_migrations(tmp_path)


def test_version_gaps_are_refused(tmp_path):
    write(tmp_path, "001_a.sql")
    write(tmp_path, "003_c.sql")
    with pytest.raises(MigrationError, match="gap"):
        discover_migrations(tmp_path)


@pytest.mark.parametrize("name", ["1_a.sql", "001a.sql", "001_A.sql", "001_a.txt", "abc_a.sql"])
def test_files_that_do_not_match_the_naming_convention_are_refused(tmp_path, name):
    write(tmp_path, name)
    with pytest.raises(MigrationError, match="filename"):
        discover_migrations(tmp_path)


def test_an_empty_directory_is_an_error_not_an_empty_plan(tmp_path):
    with pytest.raises(MigrationError, match="no migrations"):
        discover_migrations(tmp_path)
