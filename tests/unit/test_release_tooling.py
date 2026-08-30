"""The release path: the odometer, the fold, the anchor, and the page's refusals.

Nothing here shells out to a network or a real remote. Every git precondition is exercised
against a throwaway repository built in a tmp_path, because the preconditions are the part of
`make release` a reviewer cannot check by reading — they only exist as behaviour.
"""

from __future__ import annotations

import difflib
import hashlib
import importlib.util
import os
import re
import subprocess
import sys
from itertools import pairwise
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
CHANGELOG = ROOT / "CHANGELOG.md"
WEB = ROOT / "web"
STYLE = WEB / "src" / "style.css"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: @dataclass resolves its own module out of sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


release = _load("gw_release", "release.py")
render = _load("gw_render_changelog", "render-changelog.py")
assemble = _load("gw_changelog_assemble", "changelog-assemble.py")

Version = release.Version

def _section(changelog: str, tag: str) -> str:
    """One version's slice, anchor to the next `## `, for byte-comparing across a re-fold."""
    lines = changelog.splitlines()
    start = lines.index(f'<a id="{tag}"></a>')
    end = next(
        (i for i in range(start + 2, len(lines)) if lines[i].startswith("## ")), len(lines)
    )
    return "\n".join(lines[start:end]).rstrip()


SEED_CHANGELOG = """# Changelog

All notable changes to glasswell. Newest first.

## Unreleased

### 2026-08-20 — a train that already folded

- [New] something that shipped in that train
"""


# ---------------------------------------------------------------- the odometer


class TestTheOdometer:
    def test_reads_the_owner_grammar_and_refuses_everything_else(self):
        assert Version.parse("0.20") == Version(0, 20)
        assert Version.parse("1.0") == Version(1, 0)
        assert Version.parse("1.01") == Version(1, 1)
        assert Version.parse("12.99") == Version(12, 99)
        for bad in ("0.2.0", "0.1", "1.100", "01.0", "1.", "v1.0", "1.0.0", ""):
            with pytest.raises(ValueError, match="not a glasswell version"):
                Version.parse(bad)

    def test_renders_the_zero_notch_with_one_digit_and_the_rest_with_two(self):
        assert Version(1, 0).owner == "1.0"
        assert Version(1, 1).owner == "1.01"
        assert Version(1, 9).owner == "1.09"
        assert Version(1, 10).owner == "1.10"
        assert Version(1, 99).owner == "1.99"

    def test_every_reading_round_trips_through_its_own_literal(self):
        for major in (0, 1, 7):
            for tick in range(100):
                version = Version(major, tick)
                assert Version.parse(version.owner) == version

    def test_the_odometer_rolls_from_99_into_the_next_major(self):
        assert Version.parse("0.99").next().owner == "1.0"
        assert Version.parse("3.99").next().owner == "4.0"

    def test_the_release_after_a_major_is_x01_not_x1(self):
        # The owner's sequence: "…then 1.0, then 1.01, 1.02…". A `1.1` never appears.
        assert Version.parse("1.0").next().owner == "1.01"
        assert Version.parse("1.01").next().owner == "1.02"
        assert Version.parse("1.09").next().owner == "1.10"

    def test_v101_and_v110_are_nine_notches_apart_and_pep440_agrees(self):
        one_oh_one, one_ten = Version.parse("1.01"), Version.parse("1.10")

        assert one_ten.tick - one_oh_one.tick == 9
        assert one_oh_one.pep440 == "1.1"
        assert one_ten.pep440 == "1.10"
        # The collision the scheme has to survive: `1.01` normalises to `1.1`, and `1.10` must
        # not normalise onto the same string or two releases become one on PyPI-shaped tooling.
        assert one_oh_one.pep440 != one_ten.pep440
        assert one_oh_one < one_ten

    def test_pep440_ordering_is_odometer_ordering_across_the_roll(self):
        walk = [Version(0, 98), Version(0, 99), Version(1, 0), Version(1, 1), Version(1, 10)]
        as_tuples = [tuple(int(part) for part in v.pep440.split(".")) for v in walk]

        assert as_tuples == sorted(as_tuples)
        assert walk == sorted(walk)

    def test_the_pep440_spelling_is_canonical_for_every_reading(self):
        packaging = pytest.importorskip("packaging.version")
        for tick in (0, 1, 9, 10, 20, 99):
            version = Version(1, tick)
            assert str(packaging.Version(version.pep440)) == version.pep440

    def test_the_major_override_jumps_without_walking_the_odometer(self):
        assert Version.parse("0.20").next(major=True).owner == "1.0"
        assert Version.parse("1.05").next(major=True).owner == "2.0"

    def test_the_tag_the_heading_and_the_stamp_are_one_string(self):
        version = Version.parse("1.01")
        folded = release.fold(SEED_CHANGELOG, ["- [Fix] x"], version, "2026-09-01")

        assert version.tag == "v1.01"
        assert release.anchor(version) == '<a id="v1.01"></a>'
        assert f"## {version.tag} — 2026-09-01" in folded
        # What web/src/chrome/stamp.ts builds from the same literal.
        assert f"v{version.owner}+3b83fcb" == "v1.01+3b83fcb"
        assert f"/changelog/#{version.tag}" == "/changelog/#v1.01"


# ---------------------------------------------------------------- the fold


class TestTheFold:
    def test_opens_the_version_section_under_unreleased(self):
        folded = release.fold(SEED_CHANGELOG, ["- [New] a"], Version(0, 20), "2026-08-21")
        lines = folded.splitlines()

        assert lines.index("## Unreleased") < lines.index('<a id="v0.20"></a>')
        assert lines.index('<a id="v0.20"></a>') + 1 == lines.index("## v0.20 — 2026-08-21")

    def test_moves_the_dated_sections_beneath_the_new_heading(self):
        folded = release.fold(SEED_CHANGELOG, ["- [New] a"], Version(0, 20), "2026-08-21")
        lines = folded.splitlines()

        assert lines.index("## v0.20 — 2026-08-21") < lines.index(
            "### 2026-08-20 — a train that already folded"
        )
        # And Unreleased is left empty, so the next train has somewhere to land.
        between = lines[lines.index("## Unreleased") + 1 : lines.index('<a id="v0.20"></a>')]
        assert [line for line in between if line.strip()] == []

    def test_the_fragment_entries_come_before_the_sections_that_moved(self):
        folded = release.fold(
            SEED_CHANGELOG, ["- [New] pending entry"], Version(0, 20), "2026-08-21"
        )
        lines = folded.splitlines()

        assert lines.index("- [New] pending entry") < lines.index(
            "### 2026-08-20 — a train that already folded"
        )

    def test_a_second_release_folds_above_the_first_and_leaves_it_alone(self):
        first = release.fold(SEED_CHANGELOG, ["- [New] a"], Version(0, 20), "2026-08-21")
        second = release.fold(first, ["- [Fix] b"], Version(0, 21), "2026-08-22")
        lines = second.splitlines()

        assert lines.index("## v0.21 — 2026-08-22") < lines.index("## v0.20 — 2026-08-21")
        assert lines.index("- [Fix] b") < lines.index("- [New] a")
        # "leaves it alone" means byte-identical, not merely still present: a substring check
        # is blind to the anchor relocation gate-rel N1 found by running two real releases.
        assert _section(first, "v0.20") == _section(second, "v0.20")

    def test_the_previous_versions_anchor_stays_with_its_own_heading(self):
        """gate-rel N1: the fold used to drag it into the new section and leave a blank line."""
        first = release.fold(SEED_CHANGELOG, ["- [New] a"], Version(0, 20), "2026-08-21")
        second = release.fold(first, ["- [Fix] b"], Version(0, 21), "2026-08-22")
        lines = second.splitlines()

        for tag in ("v0.20", "v0.21"):
            anchor = lines.index(f'<a id="{tag}"></a>')
            assert lines[anchor + 1].startswith(f"## {tag} — "), lines[anchor : anchor + 2]
        assert second.count('<a id="v0.20"></a>') == 1

    def test_a_twice_folded_document_still_parses_as_the_page_grammar(self, tmp_path):
        # Nothing re-parsed a twice-folded changelog before, which is why N1 was invisible.
        # Versions derive from the live document's own head: folding a version the real
        # CHANGELOG already carries would fabricate a duplicate release (broke at v0.20).
        base = render.parse(CHANGELOG)
        if len(base.releases) > 1:
            head = Version.parse(base.releases[1].label.lstrip("v"))
        else:
            head = Version(0, 19)
        one, two, three = head.next(), head.next().next(), head.next().next().next()
        first = release.fold(CHANGELOG.read_text(), ["- [New] a"], one, "2026-08-21")
        second = release.fold(first, ["- [Fix] b"], two, "2026-08-22")
        third = release.fold(second, ["- [Change] c"], three, "2026-08-23")
        target = tmp_path / "CHANGELOG.md"
        target.write_text(third)

        doc = render.parse(target)
        assert [holder.label for holder in doc.releases[:4]] == [
            "Unreleased",
            f"v{three.owner}",
            f"v{two.owner}",
            f"v{one.owner}",
        ]
        html = render.render_html(doc, target)
        for version in (one, two, three):
            assert html.count(f'<h2 id="v{version.owner}"') == 1

    def test_the_fold_is_a_pure_insertion_and_rewrites_no_moved_line(self):
        """The highest-consequence property in the change set (gate-rel F5)."""
        original = CHANGELOG.read_text()
        folded = release.fold(
            original, ["- [New] the release tooling"], Version(0, 20), "2026-08-21"
        )
        before, after = original.splitlines(), folded.splitlines()

        edits = [
            operation
            for operation in difflib.SequenceMatcher(None, before, after).get_opcodes()
            if operation[0] != "equal"
        ]
        assert edits, "the fold changed nothing at all"
        assert all(operation[0] == "insert" for operation in edits), edits

    def test_the_moved_region_is_byte_identical_and_contiguous(self):
        original = CHANGELOG.read_text()
        lines = original.splitlines()
        moved = lines[lines.index("## Unreleased") + 1 :]
        while moved and not moved[0].strip():
            moved.pop(0)
        while moved and not moved[-1].strip():
            moved.pop()
        blob = "\n".join(moved)
        folded = release.fold(original, ["- [New] a"], Version(0, 20), "2026-08-21")

        assert len(moved) > 1000, len(moved)  # the fixture really is the whole changelog
        assert folded.count(blob) == 1
        assert hashlib.sha256(blob.encode()).hexdigest() == hashlib.sha256(
            "\n".join(folded.splitlines()[-len(moved) :]).encode()
        ).hexdigest()

    def test_the_entries_are_untouched_bytes_not_reflowed_prose(self):
        entries = ["- [Change] one", "         wrapped at nine spaces because Change is nine"]
        folded = release.fold(SEED_CHANGELOG, entries, Version(0, 20), "2026-08-21")

        for line in entries:
            assert line in folded.splitlines()

    def test_refuses_a_changelog_with_no_unreleased_heading(self):
        with pytest.raises(SystemExit, match="no '## Unreleased'"):
            release.fold("# Changelog\n", [], Version(0, 20), "2026-08-21")

    def test_the_folded_document_still_parses_as_the_page_grammar(self, tmp_path):
        # Fold at the version AFTER the live document's head — see the twice-folded test.
        base = render.parse(CHANGELOG)
        if len(base.releases) > 1:
            head = Version.parse(base.releases[1].label.lstrip("v"))
        else:
            head = Version(0, 19)
        nxt = head.next()
        folded = release.fold(
            CHANGELOG.read_text(), ["- [New] the release tooling"], nxt, "2026-08-21"
        )
        target = tmp_path / "CHANGELOG.md"
        target.write_text(folded)

        doc = render.parse(target)
        assert doc.releases[0].label == "Unreleased"
        assert doc.releases[0].empty
        assert doc.releases[1].label == f"v{nxt.owner}"
        # The folded entry must land in the new release, whether Unreleased held dated
        # trains (pre-v0.20 shape) or only flat entries (post-v0.20 shape).
        folded_texts = [entry.text for entry in doc.releases[1].blocks] + [
            entry.text for train in doc.releases[1].trains for entry in train.blocks
        ]
        assert "the release tooling" in folded_texts

    def test_bumps_pyproject_to_the_pep440_spelling(self):
        text = '[project]\nname = "glasswell"\nversion = "0.1.0"\n'

        assert 'version = "1.1"' in release.bump_pyproject(text, Version(1, 1))
        assert 'version = "1.10"' in release.bump_pyproject(text, Version(1, 10))

    def test_refuses_a_pyproject_with_no_version_line(self):
        with pytest.raises(SystemExit, match=r"no `version"):
            release.bump_pyproject("[project]\n", Version(0, 20))


# -------------------------------------------------------- duplicated release surfaces


def _write_release_surfaces(root: Path, version: str = "v0.47") -> None:
    (root / "README.md").write_text(
        f'<img src="https://img.shields.io/badge/release-{version}-blue" '
        f'alt="Release: {version}">\nHistorical note: {version} stays historical.\n'
    )
    (root / "STATUS.md").write_text(
        "# Current status\n\n"
        f"Reconciled on **2026-08-23** against the {version} release line, the checked-in "
        "OpenAPI\nsnapshot, and current `main` history. This is the short current-state "
        "ledger.\n\n"
        "## Shipped baseline\n\n"
        f"- **Release line:** 28 tagged releases, v0.20 through {version}, cut 2026-08-21 "
        "through\n  2026-08-23.\n"
    )
    (root / "ROADMAP.md").write_text(
        "# Roadmap\n\n"
        f"28 tagged releases, v0.20 through {version}, cut from 2026-08-21 through "
        "2026-08-23, run\nthe deployed slice.\n"
    )
    (root / "llms.txt").write_text(
        f"**Status: in build, release line {version}.** Current capabilities follow.\n"
    )


class TestReleaseSurfaceSynchronization:
    def test_updates_owned_markers_without_rewriting_historical_mentions(
        self, tmp_path, monkeypatch
    ):
        _write_release_surfaces(tmp_path)
        monkeypatch.setattr(release, "tagged_release_count", lambda root: 28)

        updates, blockers = release.sync_release_surfaces(
            tmp_path, Version(0, 47), Version(0, 48), "2026-08-24"
        )

        assert blockers == []
        assert 'release-v0.48-blue" alt="Release: v0.48"' in updates[
            tmp_path / "README.md"
        ]
        assert "Historical note: v0.47 stays historical." in updates[tmp_path / "README.md"]
        assert "against the v0.48 release line" in updates[tmp_path / "STATUS.md"]
        assert "29 tagged releases, v0.20 through v0.48" in updates[tmp_path / "STATUS.md"]
        assert "through\n  2026-08-24." in updates[tmp_path / "STATUS.md"]
        assert "29 tagged releases, v0.20 through v0.48" in updates[tmp_path / "ROADMAP.md"]
        assert "release line v0.48" in updates[tmp_path / "llms.txt"]
        assert "v0.48" not in (tmp_path / "README.md").read_text(), "rendering must be pure"

    def test_refuses_an_ambiguous_marker_instead_of_guessing(self, tmp_path, monkeypatch):
        _write_release_surfaces(tmp_path)
        llms = tmp_path / "llms.txt"
        llms.write_text(llms.read_text() * 2)
        monkeypatch.setattr(release, "tagged_release_count", lambda root: 28)

        updates, blockers = release.sync_release_surfaces(
            tmp_path, Version(0, 47), Version(0, 48), "2026-08-24"
        )

        assert updates == {}
        assert blockers == [
            "llms.txt: expected exactly one machine-readable release status; found 2"
        ]

    def test_refuses_a_partial_collateral_set(self, tmp_path):
        (tmp_path / "README.md").write_text("only one surface\n")

        updates, blockers = release.sync_release_surfaces(
            tmp_path, Version(0, 47), Version(0, 48), "2026-08-24"
        )

        assert updates == {}
        assert blockers == [
            "release collateral is incomplete; missing STATUS.md, ROADMAP.md, llms.txt"
        ]


# ---------------------------------------------------------------- preconditions


def _pending(root: Path) -> list[Path]:
    return [root / "changelog.d" / "a-track.md"]


def _repo(tmp_path: Path) -> Path:
    """A throwaway main + origin/main pair, clean, with one fragment pending."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", origin], check=True, capture_output=True)
    root = tmp_path / "repo"
    root.mkdir()
    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    run("init", "-b", "main")
    run("config", "user.email", "ryan@rfxn.com")
    run("config", "user.name", "Ryan MacDonald")
    (root / "CHANGELOG.md").write_text(SEED_CHANGELOG)
    (root / "pyproject.toml").write_text('[project]\nname = "glasswell"\nversion = "0.1.0"\n')
    (root / "scripts").mkdir()
    for script in ("changelog-assemble.py", "render-changelog.py"):
        (root / "scripts" / script).write_text((SCRIPTS / script).read_text())
    fragments = root / "changelog.d"
    fragments.mkdir()
    (fragments / "README.md").write_text("not a fragment\n")
    (fragments / "a-track.md").write_text("- [New] the first thing\n- [Fix] the second thing\n")
    run("add", "-A")
    run("commit", "-m", "seed")
    run("remote", "add", "origin", str(origin))
    run("push", "-q", "origin", "main")
    return root


def _with_migration(root: Path, body: str, name: str | None = None) -> Path:
    directory = root / release.MIGRATIONS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (name or SHIPPED_MIGRATION.name)
    path.write_text(body, encoding="utf-8")

    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

    run("add", "-A")
    run("commit", "-qm", "migration")
    run("push", "-q", "origin", "main")
    return path


MIGRATIONS = Path(release.__file__).resolve().parents[1] / release.MIGRATIONS_DIR
REPOINTED_TAG = "v0.66"
REPOINTED_COMMIT = "c8cffbc344e1ea36e454e43f3c0a4d7696aa1c0a"

# The evidence fields as the migration writes them, matched by shape rather than by value, so
# the pair below can be built whether or not the file has been repointed yet.
EVIDENCE = re.compile(
    r"(select rule_id, date '\d{4}-\d{2}-\d{2}', ')(?P<tag>[^']+)(',\s*\n\s*')"
    r"(?P<commit>[0-9a-f]{40})(')"
)


def _evidence_migration() -> Path:
    """The newest migration that registers rule publication evidence.

    Found rather than named: a migration number is assigned by merge order, and this branch's
    has already moved once. A filename literal here is the same anti-pattern the repo-wide pin
    below exists to remove, and it would go stale at the next renumber rather than at the next
    real change.
    """
    found = [path for path in sorted(MIGRATIONS.glob("*.sql")) if EVIDENCE.search(
        path.read_text(encoding="utf-8")
    )]
    assert found, "no migration registers conformance-rule publication evidence"
    return found[-1]


SHIPPED_MIGRATION = _evidence_migration()


def _with_evidence(text: str, *, tag: str, commit: str) -> str:
    replaced, count = EVIDENCE.subn(
        lambda match: f"{match.group(1)}{tag}{match.group(3)}{commit}{match.group(5)}", text
    )
    assert count == 1, f"expected one evidence insert to rewrite, matched {count}"
    return replaced


def _pair() -> tuple[str, str]:
    """The two states of the real migration: as a branch writes it, and after the repoint.

    Derived from the shipped file rather than read out of it, because a test that asserts what
    the file contains today inverts the day the integrator does the thing the file asks for.
    """
    text = SHIPPED_MIGRATION.read_text(encoding="utf-8")
    return (
        _with_evidence(
            text,
            tag=release.PLACEHOLDER_EVIDENCE_TAG,
            commit=release.PLACEHOLDER_EVIDENCE_COMMIT,
        ),
        _with_evidence(text, tag=REPOINTED_TAG, commit=REPOINTED_COMMIT),
    )


class TestPlaceholderPublicationEvidence:
    """N-1: a branch cannot know its release tag, so it writes a placeholder — and a placeholder
    that reaches a production migrate is permanent, because the table is append-only. The
    release gate is what turns that silent falsehood into a loud refusal.

    Two rules learned the hard way, both from this class's own earlier versions. The behaviour
    is pinned, never the file's current contents: an assertion that the migration *contains* the
    placeholder is true today and false the moment the merge train does what the file asks,
    which turns the correct action into a red suite. And the cases that need the real artifact
    drive it — the positive case once used a synthetic three-line blob with no header, which is
    exactly why the guard's own bare-word scan matching the header prose got through.
    """

    def test_the_placeholder_state_of_the_real_migration_blocks_the_release(self, tmp_path):
        placeholder, _ = _pair()
        root = _repo(tmp_path)
        _with_migration(root, placeholder)

        blockers = release.preconditions(root, _pending(root), Version(0, 66))

        assert any(release.PLACEHOLDER_EVIDENCE_TAG in blocker for blocker in blockers)
        assert any(SHIPPED_MIGRATION.name in blocker for blocker in blockers)
        # The refusal names the tag to repoint to, so the fix needs no second lookup.
        assert any(REPOINTED_TAG in blocker for blocker in blockers)

    def test_the_repointed_state_of_the_real_migration_releases(self, tmp_path):
        """The one that matters: doing exactly what the refusal asks must clear the refusal."""
        placeholder, repointed = _pair()
        assert placeholder != repointed, "the pair is not a pair; the rewrite matched nothing"
        root = _repo(tmp_path)
        _with_migration(root, repointed)

        assert release.preconditions(root, _pending(root), Version(0, 66)) == []
        # The header still explains the scheme by name, and prose is not evidence.
        assert release.PLACEHOLDER_EVIDENCE_TAG in repointed

    def test_a_half_repoint_of_the_real_migration_still_blocks(self, tmp_path):
        """Either literal alone is a false claim, so either alone refuses."""
        text = SHIPPED_MIGRATION.read_text(encoding="utf-8")
        halves = (
            _with_evidence(
                text, tag=REPOINTED_TAG, commit=release.PLACEHOLDER_EVIDENCE_COMMIT
            ),
            _with_evidence(
                text, tag=release.PLACEHOLDER_EVIDENCE_TAG, commit=REPOINTED_COMMIT
            ),
        )
        for index, half in enumerate(halves):
            root = _repo(tmp_path / f"half-{index}")
            _with_migration(root, half)

            blockers = release.preconditions(root, _pending(root), Version(0, 66))
            assert any(release.PLACEHOLDER_EVIDENCE_TAG in blocker for blocker in blockers)

    def test_no_migration_quotes_a_placeholder_outside_its_evidence_insert(self):
        """R-4: the pin is repo-wide, not this migration by name.

        A quoted literal in any migration's header re-arms the guard for the whole repository,
        and the track that wrote it would not find out until its own merge train. `<= 1` rather
        than `== 1` so a repointed migration — zero occurrences — passes exactly as a
        placeholder-carrying one does.
        """
        migrations = sorted(MIGRATIONS.glob("*.sql"))
        assert migrations, "no migrations found; this pin would be vacuous"
        for path in migrations:
            text = path.read_text(encoding="utf-8")
            # A migration with no evidence insert has no statement, so `header` is the whole
            # file and any quoted literal in it is caught — which is the correct answer.
            header, _, _ = text.partition("insert into lineage.conformance_rule_publications")
            for literal in (
                f"'{release.PLACEHOLDER_EVIDENCE_TAG}'",
                f"'{release.PLACEHOLDER_EVIDENCE_COMMIT}'",
            ):
                assert text.count(literal) <= 1, f"{path.name} quotes {literal} more than once"
                assert literal not in header, (
                    f"{path.name} quotes {literal} above its evidence insert, which re-arms "
                    "the release guard through prose"
                )

    def test_prose_naming_the_placeholder_does_not_block(self, tmp_path):
        """R-1 in one line: the guard reads the quoted SQL literal, never the word."""
        root = _repo(tmp_path)
        _with_migration(
            root,
            "-- this migration once carried UNRELEASED evidence and no longer does\n"
            "select 1;\n",
        )

        assert release.preconditions(root, _pending(root), Version(0, 66)) == []

    def test_a_longer_all_zero_digest_is_not_the_placeholder_commit(self, tmp_path):
        """A forty-zero run is a substring of any longer all-zero digest; the quotes are what
        make the two different values rather than one prefix of the other."""
        root = _repo(tmp_path)
        _with_migration(root, f"select '{'0' * 64}' as document_sha256;\n")

        assert release.preconditions(root, _pending(root), Version(0, 66)) == []

    def test_a_tree_with_no_migrations_directory_is_not_blocked(self, tmp_path):
        """The guard is a scan, not a requirement: a repo without migrations releases."""
        root = _repo(tmp_path)

        assert release.preconditions(root, _pending(root), Version(0, 66)) == []

    def test_the_scan_reaches_only_the_migrations_directory(self, tmp_path):
        """Fixture helpers seed their own harness evidence and must never be repointed."""
        _, repointed = _pair()
        root = _repo(tmp_path)
        (root / "tests" / "support").mkdir(parents=True)
        (root / "tests" / "support" / "seed.py").write_text(
            f"TAG = '{release.PLACEHOLDER_EVIDENCE_TAG}'\n", encoding="utf-8"
        )
        _with_migration(root, repointed)

        assert release.preconditions(root, _pending(root), Version(0, 66)) == []


class TestThePreconditions:
    def test_a_clean_level_main_with_a_fragment_pending_has_no_blockers(self, tmp_path):
        root = _repo(tmp_path)
        assert release.preconditions(root, _pending(root), Version(0, 20)) == []

    def test_refuses_a_topic_branch(self, tmp_path):
        root = _repo(tmp_path)
        subprocess.run(["git", "checkout", "-qb", "topic"], cwd=root, check=True)

        blockers = release.preconditions(root, _pending(root), Version(0, 20))
        assert any("not 'main'" in blocker for blocker in blockers)

    def test_refuses_a_dirty_tree_and_names_the_paths(self, tmp_path):
        root = _repo(tmp_path)
        (root / "scratch.txt").write_text("uncommitted\n")

        blockers = release.preconditions(root, _pending(root), Version(0, 20))
        assert any("not clean" in blocker for blocker in blockers)
        # The whole path, not the path minus its first letter: git's porcelain opens every
        # line with two status columns, and stripping them off by eye eats one character.
        assert any("(1 path(s): scratch.txt)" in blocker for blocker in blockers)

    def test_names_a_modified_tracked_file_by_its_whole_name(self, tmp_path):
        root = _repo(tmp_path)
        (root / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')

        blockers = release.preconditions(root, _pending(root), Version(0, 20))
        assert any("pyproject.toml" in blocker for blocker in blockers)

    def test_refuses_when_no_fragment_is_pending(self, tmp_path):
        root = _repo(tmp_path)
        blockers = release.preconditions(root, [], Version(0, 20))
        assert any("no fragment" in blocker for blocker in blockers)

    def test_refuses_a_head_the_remote_has_never_seen(self, tmp_path):
        root = _repo(tmp_path)
        (root / "CHANGELOG.md").write_text(SEED_CHANGELOG + "\n")
        subprocess.run(["git", "commit", "-aqm", "ahead"], cwd=root, check=True)

        blockers = release.preconditions(root, _pending(root), Version(0, 20))
        assert any("1 ahead of and 0 behind origin/main" in blocker for blocker in blockers)

    def test_refuses_a_tag_the_odometer_has_already_passed(self, tmp_path):
        root = _repo(tmp_path)
        subprocess.run(["git", "tag", "-a", "v0.20", "-m", "x"], cwd=root, check=True)

        blockers = release.preconditions(root, _pending(root), Version(0, 20))
        assert any("already exists" in blocker for blocker in blockers)

    def test_reports_every_reason_at_once_rather_than_the_first(self, tmp_path):
        root = _repo(tmp_path)
        subprocess.run(["git", "checkout", "-qb", "topic"], cwd=root, check=True)
        (root / "scratch.txt").write_text("uncommitted\n")

        assert len(release.preconditions(root, [], Version(0, 20))) == 3


class TestTheReleaseRun:
    def test_a_dry_run_on_a_blocked_tree_prints_and_writes_nothing(self, tmp_path, capsys):
        root = _repo(tmp_path)
        subprocess.run(["git", "checkout", "-qb", "topic"], cwd=root, check=True)
        before = (root / "CHANGELOG.md").read_text()

        assert release.main(["--dry-run", "--root", str(root), "--date", "2026-08-21"]) == 0

        out = capsys.readouterr().out
        assert "would cut v0.20" in out
        assert "BLOCK" in out
        assert "- [New] the first thing" in out
        assert (root / "CHANGELOG.md").read_text() == before
        assert not (root / "VERSION").exists()
        assert (root / "changelog.d" / "a-track.md").exists()

    def test_a_blocked_real_run_exits_nonzero_and_changes_nothing(self, tmp_path, capsys):
        root = _repo(tmp_path)
        (root / "scratch.txt").write_text("uncommitted\n")
        before = (root / "CHANGELOG.md").read_text()

        assert release.main(["--root", str(root), "--date", "2026-08-21"]) == 1
        assert "refusing to release v0.20" in capsys.readouterr().err
        assert (root / "CHANGELOG.md").read_text() == before
        assert not (root / "VERSION").exists()

    def test_the_first_release_seeds_the_odometer_at_0_20(self, tmp_path):
        root = _repo(tmp_path)

        assert release.main(["--root", str(root), "--date", "2026-08-21"]) == 0

        assert (root / "VERSION").read_text() == "0.20\n"
        assert 'version = "0.20"' in (root / "pyproject.toml").read_text()
        assert "## v0.20 — 2026-08-21" in (root / "CHANGELOG.md").read_text()
        assert not (root / "changelog.d" / "a-track.md").exists()
        assert (root / "changelog.d" / "README.md").exists()

    def test_the_commit_and_the_annotated_tag_carry_the_entries(self, tmp_path):
        root = _repo(tmp_path)
        release.main(["--root", str(root), "--date", "2026-08-21"])

        def show(ref: str, fmt: str) -> str:
            return subprocess.run(
                ["git", "log", "-1", f"--format={fmt}", ref],
                cwd=root,
                capture_output=True,
                text=True,
            ).stdout

        assert show("HEAD", "%s").strip() == "Release v0.20"
        assert "- [New] the first thing" in show("HEAD", "%b")
        tag = subprocess.run(
            ["git", "cat-file", "tag", "v0.20"], cwd=root, capture_output=True, text=True
        ).stdout
        assert "glasswell v0.20 — 2026-08-21" in tag
        assert "- [Fix] the second thing" in tag
        annotated = subprocess.run(
            ["git", "rev-parse", "v0.20^{tag}"], cwd=root, capture_output=True
        )
        assert annotated.returncode == 0, "the tag must be annotated, not lightweight"

    def test_the_second_release_turns_the_notch_once(self, tmp_path):
        root = _repo(tmp_path)
        release.main(["--root", str(root), "--date", "2026-08-21"])
        subprocess.run(["git", "push", "-q", "origin", "main"], cwd=root, check=True)
        _write_release_surfaces(root, "v0.20")
        (root / "changelog.d" / "b-track.md").write_text("- [Fix] a later thing\n")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "next"], cwd=root, check=True)
        subprocess.run(["git", "push", "-q", "origin", "main"], cwd=root, check=True)

        assert release.main(["--root", str(root), "--date", "2026-08-22"]) == 0
        assert (root / "VERSION").read_text() == "0.21\n"
        assert "release-v0.21-blue" in (root / "README.md").read_text()
        assert "2 tagged releases, v0.20 through v0.21" in (root / "STATUS.md").read_text()
        committed = subprocess.run(
            ["git", "show", "--format=", "--name-only", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        assert set(release.RELEASE_SURFACE_FILES) <= set(committed)

    def test_refuses_to_turn_the_odometer_backwards(self, tmp_path):
        root = _repo(tmp_path)
        (root / "VERSION").write_text("0.30\n")

        with pytest.raises(SystemExit, match="only turns forward"):
            release.main(["--root", str(root), "--set", "0.21"])

    def test_set_and_major_together_are_refused(self, tmp_path):
        root = _repo(tmp_path)
        with pytest.raises(SystemExit, match="pass one"):
            release.main(["--root", str(root), "--set", "1.0", "--major"])

    def test_a_version_outside_the_grammar_refuses_in_prose_rather_than_raising(self, tmp_path):
        # gate-rel F7: this used to surface an uncaught ValueError traceback.
        root = _repo(tmp_path)
        with pytest.raises(SystemExit, match="not a glasswell version") as refusal:
            release.main(["--root", str(root), "--set", "1.100"])

        assert not isinstance(refusal.value.__cause__, ValueError)
        assert "--set" in str(refusal.value)

    def test_a_pre_scheme_version_file_refuses_in_prose_rather_than_raising(self, tmp_path):
        # `0.1.0` is exactly what a half-migrated tree still carries.
        root = _repo(tmp_path)
        (root / "VERSION").write_text("0.1.0\n")

        with pytest.raises(SystemExit, match="not a glasswell version") as refusal:
            release.main(["--root", str(root)])

        assert "VERSION" in str(refusal.value)


# ------------------------------------------------- gate-rel B1: the fragment-to-tag seam


BOGUS_FRAGMENT = (
    "- [New] a perfectly valid first line the assembler will accept\n"
    "- [Bogus] a tag the page parser will refuse, on line 2 of the fragment\n"
    "- [Fix] and a valid one after it\n"
)


def _plant(root: Path, name: str, body: str) -> Path:
    fragment = root / "changelog.d" / name
    fragment.write_text(body)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "plant"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=root, check=True)
    return fragment


def _snapshot(root: Path) -> dict[str, object]:
    tags = subprocess.run(
        ["git", "tag", "-l"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.split()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
    return {
        "tags": tags,
        "head": head,
        "changelog": (root / "CHANGELOG.md").read_text(),
        "pyproject": (root / "pyproject.toml").read_text(),
        "version": (root / "VERSION").read_text() if (root / "VERSION").exists() else None,
        "fragments": sorted(path.name for path in (root / "changelog.d").iterdir()),
    }


class TestABadFragmentLineNeverReachesATag:
    """gate-rel B1, reproduced: `[Bogus]` on line 2 used to survive all the way to a cut tag."""

    def test_the_release_refuses_and_leaves_no_tag_and_no_write(self, tmp_path, capsys):
        root = _repo(tmp_path)
        _plant(root, "a-track.md", BOGUS_FRAGMENT)
        before = _snapshot(root)

        assert release.main(["--root", str(root), "--date", "2026-08-21"]) == 1

        refusal = capsys.readouterr().err
        assert "unknown entry tag [Bogus]" in refusal
        assert "a-track.md:2" in refusal
        assert _snapshot(root) == before
        assert before["tags"] == []

    def test_check_refuses_it_too_so_ship_stops_before_the_build(self, tmp_path, capsys):
        root = _repo(tmp_path)
        _plant(root, "a-track.md", BOGUS_FRAGMENT)
        before = _snapshot(root)

        assert release.main(["--check", "--root", str(root)]) == 1
        assert "unknown entry tag [Bogus]" in capsys.readouterr().err
        assert _snapshot(root) == before

    def test_the_refusal_names_the_line_the_page_would_have_named(self, tmp_path):
        root = _repo(tmp_path)
        fragment = root / "changelog.d" / "a-track.md"
        fragment.write_text(BOGUS_FRAGMENT)

        with pytest.raises(SystemExit) as refusal:
            release.load_assembler(root).read_entries(fragment)

        assert f"{fragment}:2:" in str(refusal.value)
        assert "- [Bogus] a tag the page parser" in str(refusal.value)

    @pytest.mark.parametrize(
        ("body", "why"),
        [
            (BOGUS_FRAGMENT, "unknown entry tag [Bogus]"),
            ("- [New] fine\n* a bullet in the wrong flavour\n", "not the changelog grammar"),
            ("- [New] fine\n| a | table |\n", "not the changelog grammar"),
            ("- [New] fine\n```python\n", "not the changelog grammar"),
            ("- [New] fine\n\n      an orphan continuation\n", "indented line with no entry"),
            ("- [New] a `span that never closes\n", "code span opens and never closes"),
            ("      an indented first line\n", "indented line with no entry"),
            ("just prose, no entry at all\n", "no changelog entry in this fragment"),
            ("\n", "an empty fragment"),
        ],
    )
    def test_every_shape_the_page_refuses_is_refused_at_the_fragment(self, tmp_path, body, why):
        fragment = tmp_path / "a-track.md"
        fragment.write_text(body)

        with pytest.raises(SystemExit, match=re.escape(why)):
            render.check_fragment(fragment)

    def test_a_good_fragment_survives_unchanged_to_the_byte(self, tmp_path):
        body = (
            "- [Change] one entry, soft-wrapped at a clean phrase boundary;\n"
            "         continuation indent nine spaces because Change is nine\n"
            "- [Fix] and `a code span that wraps\n"
            "      across the line break` the way the real file does\n"
        )
        fragment = tmp_path / "a-track.md"
        fragment.write_text(body)

        assert render.check_fragment(fragment) == body.strip("\n")

    def test_the_release_still_refuses_a_changelog_a_hand_edit_broke(self, tmp_path, capsys):
        # Belt to the fragment check's braces: the render gate reads the whole candidate
        # document, so a bad line already sitting in CHANGELOG.md blocks the tag too.
        root = _repo(tmp_path)
        (root / "CHANGELOG.md").write_text(
            SEED_CHANGELOG.replace("- [New] something", "- [Bogus] something")
        )
        subprocess.run(["git", "commit", "-aqm", "hand edit"], cwd=root, check=True)
        subprocess.run(["git", "push", "-q", "origin", "main"], cwd=root, check=True)
        before = _snapshot(root)

        assert release.main(["--root", str(root), "--date", "2026-08-21"]) == 1

        refusal = capsys.readouterr().err
        assert "would not render" in refusal
        assert "unknown entry tag [Bogus]" in refusal
        assert _snapshot(root) == before


class TestTheAssembler:
    """gate-rel F8: the file carrying B1 had no coverage of its own."""

    def test_pending_fragments_skips_the_readme_and_sorts_by_filename(self, tmp_path):
        for name in ("README.md", "20-second.md", "10-first.md", "notes.txt"):
            (tmp_path / name).write_text("- [New] x\n")

        assert [path.name for path in assemble.pending_fragments(tmp_path)] == [
            "10-first.md",
            "20-second.md",
        ]

    def test_read_entries_is_the_page_grammar_not_a_second_one(self, tmp_path):
        fragment = tmp_path / "a-track.md"
        fragment.write_text(BOGUS_FRAGMENT)

        with pytest.raises(SystemExit, match=re.escape("unknown entry tag [Bogus]")):
            assemble.read_entries(fragment)
        assert assemble.grammar() is render_module_under_assemble()

    def test_lint_passes_every_pending_fragment_in_this_repository(self, capsys):
        assert assemble.main(["--lint"]) == 0
        assert "parse against the changelog grammar" in capsys.readouterr().out

    def test_lint_refuses_a_bad_fragment_and_names_the_line(self, tmp_path, capsys):
        (tmp_path / "README.md").write_text("not a fragment\n")
        (tmp_path / "a-track.md").write_text(BOGUS_FRAGMENT)

        with pytest.raises(SystemExit, match=re.escape("unknown entry tag [Bogus]")):
            assemble.main(["--lint", "--fragments", str(tmp_path)])

    def test_check_fails_while_fragments_pend_and_passes_when_they_do_not(self, tmp_path, capsys):
        (tmp_path / "README.md").write_text("not a fragment\n")
        assert assemble.main(["--check", "--fragments", str(tmp_path)]) == 0

        (tmp_path / "a-track.md").write_text("- [New] pending\n")
        assert assemble.main(["--check", "--fragments", str(tmp_path)]) == 1
        assert "pending:" in capsys.readouterr().out

    def test_the_dated_fold_requires_a_title(self, tmp_path):
        (tmp_path / "a-track.md").write_text("- [New] pending\n")
        with pytest.raises(SystemExit, match="--title is required"):
            assemble.main(["--fragments", str(tmp_path), "--changelog", str(tmp_path / "C.md")])

    def test_the_dated_fold_appends_into_a_heading_it_already_opened(self, tmp_path):
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(SEED_CHANGELOG)
        first = tmp_path / "10-a.md"
        first.write_text("- [New] the first\n")
        today = __import__("datetime").date.today().isoformat()

        once = assemble.fold(changelog, [first], "a train")
        changelog.write_text(once)
        second = tmp_path / "20-b.md"
        second.write_text("- [Fix] the second\n")
        twice = assemble.fold(changelog, [second], "a train")

        assert twice.count(f"### {today} — a train") == 1
        assert twice.index("- [New] the first") < twice.index("- [Fix] the second")

    def test_the_fold_refuses_a_changelog_with_no_unreleased_heading(self, tmp_path):
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("# Changelog\n")
        fragment = tmp_path / "a.md"
        fragment.write_text("- [New] x\n")

        with pytest.raises(SystemExit, match="no '## Unreleased'"):
            assemble.fold(changelog, [fragment], "a train")


def render_module_under_assemble():
    """The renderer instance the assembler loaded, so the identity check above means something."""
    return assemble.grammar()


class TestTheOdometerGrammarIsNotFourOpinions:
    """gate-rel N6: the pattern is written out in four places and nothing held them together."""

    SAMPLES = (
        "0.20", "1.0", "1.01", "1.09", "1.10", "1.99", "10.0", "0.99",
        "1.1", "1.100", "1", "01.2", "1.0.0", "v1.0", "", "0.2.0", "1.", "0.0-dev",
    )

    @staticmethod
    def _literal(path: Path, name: str) -> re.Pattern[str]:
        found = re.search(rf"^const {name} = /(.+)/;$", path.read_text(), re.MULTILINE)
        assert found, f"{path}: no `const {name} = /…/;` to read the grammar from"
        return re.compile(found.group(1))

    def test_python_and_typescript_accept_and_reject_the_same_strings(self):
        python = [bool(release.OWNER_LITERAL.match(s)) for s in self.SAMPLES]
        heading = [
            bool(render.VERSION_HEADING.match(f"## v{s} — 2026-08-21")) for s in self.SAMPLES
        ]
        stamp = self._literal(WEB / "src" / "chrome" / "stamp.ts", "VERSION")
        config = self._literal(WEB / "vite.config.ts", "VERSION")

        # The sample set has to exercise both verdicts, or agreement is agreement on nothing.
        assert any(python)
        assert not all(python)
        assert heading == python
        assert [bool(stamp.match(s)) for s in self.SAMPLES] == python
        assert [bool(config.match(s)) for s in self.SAMPLES] == python

    def test_the_grammar_the_release_writes_is_the_grammar_the_page_reads(self):
        for tick in (0, 1, 9, 10, 99):
            version = Version(1, tick)
            heading = f"## {version.tag} — 2026-08-21"

            assert render.VERSION_HEADING.match(heading)
            assert render.VERSION_HEADING.match(heading).group(1) == version.tag
            assert release.anchor(version) == f'<a id="{version.tag}"></a>'


# ---------------------------------------------------------------- the page


def _write(tmp_path: Path, body: str) -> Path:
    target = tmp_path / "CHANGELOG.md"
    target.write_text(body)
    return target


class TestThePageGrammar:
    def test_the_repository_changelog_parses(self):
        doc = render.parse(CHANGELOG)
        tags = {
            block.tag
            for release_ in doc.releases
            for train in release_.trains
            for block in train.blocks
            if isinstance(block, render.Entry)
        }

        assert doc.releases
        assert tags == set(render.TAGS)

    def test_the_fragment_tags_and_the_page_tags_are_one_list(self):
        # A fragment the assembler admits and the page then refuses breaks the release, not
        # the fold — by which point the tag is already cut.
        assert assemble.TAGS == render.TAGS

    def test_a_malformed_entry_line_refuses_with_the_line_number(self, tmp_path):
        source = _write(
            tmp_path,
            "# Changelog\n\n## Unreleased\n\n- [New] fine\n- [Bogus] not a tag this project uses\n",
        )

        with pytest.raises(SystemExit) as refusal:
            render.parse(source)

        assert f"{source}:6:" in str(refusal.value)
        assert "unknown entry tag [Bogus]" in str(refusal.value)
        assert "[New], [Change], [Fix], [Remove]" in str(refusal.value)

    @pytest.mark.parametrize(
        ("bad", "why"),
        [
            ("* a bullet in the wrong flavour", "not the changelog grammar"),
            ("1. an ordered list", "not the changelog grammar"),
            ("| a | table |", "not the changelog grammar"),
            ("```python", "not the changelog grammar"),
            ("<div>raw html</div>", "not the changelog grammar"),
            ("> a block quote", "not the changelog grammar"),
            ("#### a fourth-level heading", "outside the grammar"),
            ("## Something Else", "not `## Unreleased`"),
            ("### not-a-date — a train", "not `### <YYYY-MM-DD>"),
        ],
    )
    def test_refuses_the_line_and_says_which_one(self, tmp_path, bad, why):
        source = _write(tmp_path, f"# Changelog\n\n## Unreleased\n\n- [New] fine\n\n{bad}\n")

        with pytest.raises(SystemExit) as refusal:
            render.parse(source)

        assert f"{source}:7:" in str(refusal.value)
        assert why in str(refusal.value)
        assert bad in str(refusal.value)

    def test_refuses_a_continuation_with_no_entry_above_it(self, tmp_path):
        source = _write(tmp_path, "# Changelog\n\n## Unreleased\n\n      orphaned continuation\n")

        with pytest.raises(SystemExit, match="indented line with no entry above it"):
            render.parse(source)

    def test_refuses_an_unbalanced_code_span(self, tmp_path):
        source = _write(
            tmp_path, "# Changelog\n\n## Unreleased\n\n- [New] a `span that never closes\n"
        )
        doc = render.parse(source)

        with pytest.raises(SystemExit) as refusal:
            render.render_html(doc, source)
        assert f"{source}:5:" in str(refusal.value)
        assert "code span opens and never closes" in str(refusal.value)

    def test_refuses_a_version_heading_with_no_anchor(self, tmp_path):
        source = _write(tmp_path, "# Changelog\n\n## Unreleased\n\n## v0.20 — 2026-08-21\n")

        with pytest.raises(SystemExit, match=re.escape('no <a id="v0.20"></a> above this')):
            render.parse(source)

    def test_refuses_an_anchor_that_names_a_different_version(self, tmp_path):
        source = _write(
            tmp_path,
            '# Changelog\n\n## Unreleased\n\n<a id="v0.21"></a>\n## v0.20 — 2026-08-21\n',
        )

        with pytest.raises(SystemExit, match=re.escape("does not name 'v0.20'")):
            render.parse(source)

    def test_refuses_a_version_heading_outside_the_odometer_grammar(self, tmp_path):
        source = _write(
            tmp_path,
            '# Changelog\n\n## Unreleased\n\n<a id="v0.2.0"></a>\n## v0.2.0 — 2026-08-21\n',
        )

        with pytest.raises(SystemExit, match=re.escape("not `## Unreleased`")):
            render.parse(source)

    def test_soft_wrapped_prose_is_one_paragraph(self, tmp_path):
        source = _write(tmp_path, "# Changelog\n\nfirst line\nsecond line\n\n## Unreleased\n")
        doc = render.parse(source)

        assert [para.text for para in doc.intro] == ["first line second line"]

    def test_a_wrapped_code_span_survives_the_join(self, tmp_path):
        source = _write(
            tmp_path,
            "# Changelog\n\n## Unreleased\n\n- [Fix] halts with `raw.fetch_failed\n"
            "      reason=host_unresolved` instead of guessing\n",
        )
        html = render.render_html(render.parse(source), source)

        assert "<code>raw.fetch_failed reason=host_unresolved</code>" in html


class TestThePageOutput:
    @pytest.fixture
    def page(self, tmp_path):
        source = _write(
            tmp_path,
            "# Changelog\n\nan intro line\n\n## Unreleased\n\n"
            '<a id="v0.20"></a>\n## v0.20 — 2026-08-21\n\n'
            "- [New] a thing with `code` and **weight**\n"
            "- [Change] another\n\n"
            "### 2026-08-20 — a dated train\n\n"
            "- [Fix] and one more\n",
        )
        return render.render_html(render.parse(source), source), source

    def test_each_version_heading_carries_its_own_id(self, page):
        html, _ = page
        assert '<h2 id="v0.20">' in html
        assert 'href="#v0.20"' in html

    def test_the_anchor_is_the_string_the_header_stamp_builds(self, page):
        html, _ = page
        # stamp.ts renders `v0.20+<hash>` and links `/changelog/#v0.20`. Same literal.
        assert 'id="v0.20"' in html
        assert "v0.2.0" not in html
        assert "0.20.0" not in html

    def test_carries_the_landmarks_a_reader_navigates_by(self, page):
        html, _ = page
        for landmark in ("<header", "<nav ", "<main ", "<footer"):
            assert landmark in html
        assert '<html lang="en"' in html
        assert 'aria-labelledby="gw-cl-navtitle"' in html
        assert 'href="#gw-releases"' in html  # the skip link
        assert '<img class="gw-mark"' in html
        assert 'alt=""' in html

    def test_the_heading_order_is_h1_then_h2_then_h3(self, page):
        html, _ = page
        levels = [int(found) for found in re.findall(r"<h([1-6])[ >]", html)]

        assert levels[0] == 1
        for previous, current in pairwise(levels):
            assert current <= previous + 1, f"heading jumped from h{previous} to h{current}"

    def test_every_id_on_the_page_is_unique(self, page):
        html, _ = page
        ids = re.findall(r'id="([^"]+)"', html)

        assert len(ids) >= 4, ids  # a stubbed renderer returns none, and 0 == 0 proves nothing
        assert len(ids) == len(set(ids))

    def test_the_empty_unreleased_section_is_not_painted(self, page):
        html, _ = page

        assert 'id="v0.20"' in html  # the page was rendered at all
        assert 'id="unreleased"' not in html


    def test_entries_carry_their_tag_as_data_not_as_colour(self, page):
        html, _ = page
        assert 'data-tag="New"' in html
        assert 'data-tag="Change"' in html
        assert "<code>code</code>" in html
        assert "<strong>weight</strong>" in html

    def test_a_repository_relative_link_is_named_rather_than_linked(self, tmp_path):
        source = _write(
            tmp_path, "# Changelog\n\n## Unreleased\n\n- [New] see [ROADMAP.md](ROADMAP.md)\n"
        )
        html = render.render_html(render.parse(source), source)

        assert '<span class="gw-cl-ref">ROADMAP.md</span>' in html
        assert 'href="ROADMAP.md"' not in html

    def test_no_inline_style_or_script_because_the_csp_refuses_both(self, page):
        html, _ = page
        # security.py: `script-src 'self'; style-src 'self'` — an inline block never runs.
        assert "<style" not in html
        assert 'src="/changelog/changelog.js"' in html
        assert 'href="/changelog/changelog.css"' in html
        assert "onclick" not in html


class TestThePageStyling:
    def test_the_palette_is_lifted_from_the_app_rather_than_copied(self):
        css = render.tokens(STYLE)
        style = STYLE.read_text()

        for token in ("--ink", "--panel", "--cyan-text", "--gw-font-mono", "--gw-space-4"):
            assert token in css
        assert ':root[data-theme="light"]' in css
        # Verbatim: the check is that these are the app's own declarations, not lookalikes.
        for declaration in ("--cyan: #5fd3e8;", "--paper: #0b1014;"):
            assert declaration in style
            assert declaration in css

    def test_the_page_css_names_only_variables_the_lifted_blocks_define(self):
        css = render.render_css(STYLE)
        declared = set(re.findall(r"(--[a-z0-9-]+):", css))
        used = set(re.findall(r"var\((--[a-z0-9-]+)", css))

        assert len(declared) > 40, len(declared)  # an empty stylesheet satisfies set() <= set()
        assert len(used) > 20, len(used)
        assert used <= declared, f"undeclared: {sorted(used - declared)}"

    def test_the_theme_script_reads_the_key_the_app_writes(self):
        # chrome/theme.ts: THEME_STORAGE_KEY = "glasswell.theme". A second page that guessed
        # a different key would disagree with the rail on every reload.
        assert '"glasswell.theme"' in render.PAGE_JS
        assert "?theme=" not in render.PAGE_JS  # it reads the parameter, it does not build one
        assert 'get("theme")' in render.PAGE_JS

    def test_writes_three_files_and_nothing_else(self, tmp_path):
        out = tmp_path / "changelog"
        assert render.main(["--changelog", str(CHANGELOG), "--out", str(out)]) == 0

        assert sorted(path.name for path in out.iterdir()) == [
            "changelog.css",
            "changelog.js",
            "index.html",
        ]


# ---------------------------------------------------------------- the deploy


DEPLOY = SCRIPTS / "deploy.sh"


def _deployable(tmp_path: Path) -> Path:
    """A repo shaped like a deploy candidate: clean, built, with deploy.sh in place."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "deploy.sh").write_bytes(DEPLOY.read_bytes())
    (root / "scripts" / "deploy.sh").chmod(0o755)
    (root / "requirements.lock").write_text("polars==1.0.0\n")
    (root / "tests" / "contract").mkdir(parents=True)
    (root / "tests" / "contract" / "openapi_snapshot.json").write_text("{}\n")
    (root / "web" / "dist" / "changelog").mkdir(parents=True)
    (root / "web" / "dist" / "index.html").write_text("<!doctype html>")
    (root / "web" / "dist" / "changelog" / "index.html").write_text("<!doctype html>")
    # Two numbered migrations make the repo head 2 — without them the "not a glasswell
    # tree" refusal fires first and masks every case below it.
    migrations = root / "src" / "glasswell" / "db" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "001_init.sql").write_text("select 1;\n")
    (migrations / "002_wells.sql").write_text("select 2;\n")
    (root / ".gitignore").write_text("web/dist/\n")
    for args in (
        ("init", "-b", "main"),
        ("config", "user.email", "ryan@rfxn.com"),
        ("config", "user.name", "Ryan MacDonald"),
        ("add", "-A"),
        ("commit", "-qm", "seed"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root


def _tag(root: Path, name: str = "v0.20") -> None:
    subprocess.run(["git", "tag", "-a", name, "-m", "x"], cwd=root, check=True)


MARKER = "deploy.sh reached ssh"


def _run_deploy(root: Path, tmp_path: Path, *args: str, **env: str):
    """Runs deploy.sh with an `ssh` on PATH that announces itself if it is ever reached.

    The refusal tests below run **without** `--dry-run` on purpose (gate-rel F3): in dry-run
    the stub is unreachable by construction, so the assertion could not fail and was proving
    nothing. Reached for real, a broken refusal walks straight into this stub and says so.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "ssh"
    fake.write_text(f"#!/bin/sh\necho '{MARKER}' >&2\nexit 99\n")
    fake.chmod(0o755)
    return subprocess.run(
        ["bash", str(root / "scripts" / "deploy.sh"), *args],
        cwd=root,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", **env},
    )


def _run_deploy_against_a_stub_host(
    root: Path, tmp_path: Path, *args: str, db_head: str = "", lock_hash: str = ""
):
    """Runs deploy.sh against a cooperative `ssh` stub, the gate-reldeploy harness shape.

    The stub logs every composed remote command, drains tar pipes so the producer is not
    SIGPIPEd, and answers the schema_migrations head query with `db_head` — so tests can
    pose gap, no-gap and garbage answers. Returns (result, call log). The host is pinned
    to an .invalid name: if the shim ever fails to intercept, nothing reaches a real box.
    """
    bin_dir = tmp_path / "stub-bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "ssh-calls.log"
    log.write_text("")
    fake = bin_dir / "ssh"
    fake.write_text(
        "#!/bin/sh\n"
        f'printf \'%s\\n\' "$2" >> "{log}"\n'
        "cat >/dev/null\n"
        'case "$2" in\n'
        '  *sha256sum*) printf \'%s\\n\' "$GW_STUB_LOCK_HASH" ;;\n'
        '  *schema_migrations*) printf \'%s\\n\' "$GW_STUB_DB_HEAD" ;;\n'
        'esac\n'
        "exit 0\n"
    )
    fake.chmod(0o755)
    result = subprocess.run(
        ["bash", str(root / "scripts" / "deploy.sh"), *args],
        cwd=root,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "GW_DEPLOY_HOST": "root@stub.invalid",
            "GW_STUB_DB_HEAD": db_head,
            "GW_STUB_LOCK_HASH": lock_hash,
        },
    )
    return result, log.read_text()


class TestTheDeployRefusals:
    def test_refuses_a_dirty_tree_before_reaching_the_host(self, tmp_path):
        root = _deployable(tmp_path)
        _tag(root)
        (root / "scratch.txt").write_text("uncommitted\n")

        result = _run_deploy(root, tmp_path)

        assert result.returncode == 1
        assert "the working tree is not clean" in result.stderr
        assert MARKER not in result.stderr

    def test_refuses_an_untagged_head_because_rolling_releases_deploy_tags(self, tmp_path):
        root = _deployable(tmp_path)

        result = _run_deploy(root, tmp_path)

        assert result.returncode == 1
        assert "HEAD carries no tag" in result.stderr
        assert MARKER not in result.stderr

    def test_the_untagged_escape_hatch_is_explicit_and_says_so(self, tmp_path):
        root = _deployable(tmp_path)

        result = _run_deploy(root, tmp_path, "--dry-run", GW_DEPLOY_ALLOW_UNTAGGED="1")

        assert result.returncode == 0
        assert "(untagged" in result.stdout

    def test_refuses_a_tree_whose_frontend_was_never_built(self, tmp_path):
        root = _deployable(tmp_path)
        _tag(root)
        (root / "web" / "dist" / "index.html").unlink()

        result = _run_deploy(root, tmp_path)

        assert result.returncode == 1
        assert "web/dist is not built" in result.stderr
        assert MARKER not in result.stderr

    def test_refuses_a_bundle_with_no_changelog_page_the_stamp_links_to(self, tmp_path):
        root = _deployable(tmp_path)
        _tag(root)
        (root / "web" / "dist" / "changelog" / "index.html").unlink()

        result = _run_deploy(root, tmp_path)

        assert result.returncode == 1
        assert "changelog/index.html is missing" in result.stderr
        assert MARKER not in result.stderr

    def test_refuses_a_bundle_older_than_the_release_it_would_carry(self, tmp_path):
        # The stamp's version and the changelog page are baked at build time, so a stale dist
        # deploys the previous release's page under this release's tag.
        root = _deployable(tmp_path)
        (root / "VERSION").write_text("0.20\n")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "version"], cwd=root, check=True)
        _tag(root)

        result = _run_deploy(root, tmp_path)

        assert result.returncode == 1
        assert "web/dist predates VERSION" in result.stderr
        assert MARKER not in result.stderr

    def test_the_stub_is_reachable_when_a_refusal_stops_refusing(self, tmp_path):
        """The guard's own guard: if the tests could never reach ssh, they prove nothing."""
        root = _deployable(tmp_path)
        _tag(root)
        script = root / "scripts" / "deploy.sh"
        script.write_text(script.read_text().replace("if [[ -n $dirty ]]; then", "if false; then"))
        (root / "scratch.txt").write_text("uncommitted\n")

        result = _run_deploy(root, tmp_path)

        assert MARKER in result.stderr, "the refusal is the only thing keeping ssh unreached"

    def test_a_clean_tagged_tree_plans_the_runbook_and_touches_no_host(self, tmp_path):
        root = _deployable(tmp_path)
        _tag(root)

        result = _run_deploy(root, tmp_path, "--dry-run", GW_DEPLOY_HOST="root@example.invalid")

        assert result.returncode == 0
        assert "deploying v0.20" in result.stdout
        assert "root@example.invalid" in result.stdout
        assert "reached ssh" not in result.stderr
        # The runbook's own shape: tar over ssh, never rsync --delete, tests/ sent separately.
        for planned in (
            "tar -x -C /opt/glasswell/src",
            "tar -x -C /opt/glasswell/web",
            "install.sh",
            "systemctl restart glasswell-api",
            "verify.sh",
            "smoke.sh",
        ):
            assert planned in result.stderr
        assert "rsync" not in result.stderr

    def test_migrations_are_opt_in(self, tmp_path):
        # A bare deploy over a gap refuses naming both heads; applying is explicit.
        root = _deployable(tmp_path)
        _tag(root)

        bare, bare_log = _run_deploy_against_a_stub_host(root, tmp_path, db_head="1")
        assert bare.returncode == 1
        assert "deploy refused: the repo carries migrations ahead of the database" in bare.stderr
        assert "(repo head 2, database 1)" in bare.stderr
        assert "pass --with-migrations to apply them" in bare.stderr
        assert "glasswell-migrate" not in bare_log

        applied, applied_log = _run_deploy_against_a_stub_host(
            root, tmp_path, "--with-migrations", db_head="1"
        )
        assert applied.returncode == 0
        assert "glasswell-migrate" in applied_log

    def test_a_current_schema_head_deploys_and_says_so(self, tmp_path):
        root = _deployable(tmp_path)
        _tag(root)

        result, log = _run_deploy_against_a_stub_host(root, tmp_path, db_head="2")

        assert result.returncode == 0
        assert "schema is current at head 002" in result.stdout
        assert "schema_migrations" in log

    def test_an_unchanged_lock_still_refreshes_project_entry_points(self, tmp_path):
        root = _deployable(tmp_path)
        _tag(root)
        lock_hash = hashlib.sha256((root / "requirements.lock").read_bytes()).hexdigest()

        result, log = _run_deploy_against_a_stub_host(
            root, tmp_path, db_head="2", lock_hash=lock_hash
        )

        assert result.returncode == 0
        assert "dependency install skipped" in result.stdout
        assert "pip install -q -e /opt/glasswell/src --no-deps" in log
        assert "pip install -q -r" not in log

    def test_a_head_answer_that_is_not_a_number_is_refused_verbatim(self, tmp_path):
        root = _deployable(tmp_path)
        _tag(root)

        result, _ = _run_deploy_against_a_stub_host(root, tmp_path, db_head="garbage")

        assert result.returncode == 1
        assert "schema_migrations head answered 'garbage', not a number" in result.stderr

    def test_the_retired_migration_skip_is_refused_before_host_access(self, tmp_path):
        root = _deployable(tmp_path)
        _tag(root)

        result = _run_deploy(root, tmp_path, "--skip-migrations")

        assert result.returncode == 2
        assert "--skip-migrations was retired" in result.stderr
        assert MARKER not in result.stderr


# Pre-055 migrations backfilled evidence for rules that already existed, so their commits
# legitimately predate the file asserting them. The merge-train rule below governs 055 onward,
# where the integrator repoints at the train and the rules are new in that same migration.
MERGE_TRAIN_ERA = 55

EVIDENCE_ROW = re.compile(r"'(?P<tag>[^']+)',\s*\n\s*'(?P<commit>[0-9a-f]{40})'")


def _merge_train_evidence() -> list[tuple[Path, str, str]]:
    """(migration, rule_id, commit) for repointed publication rows in the merge-train era."""
    rows = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if int(path.name.split("_", 1)[0]) < MERGE_TRAIN_ERA:
            continue
        text = path.read_text(encoding="utf-8")
        if "conformance_rule_publications" not in text:
            continue
        match = EVIDENCE_ROW.search(text)
        if match is None or match.group("tag") == release.PLACEHOLDER_EVIDENCE_TAG:
            continue
        for rule in re.findall(r"'(cr_[a-z0-9_]+)'", text):
            rows.append((path, rule, match.group("commit")))
    return rows


def test_repointed_evidence_cites_a_commit_that_carries_the_rule() -> None:
    """A merge-train repoint names the first commit containing the rule, not the head before it.

    `evidence_commit` is provenance in an append-only table, so a commit that does not carry the
    rule is a permanent claim nobody can check out and verify. The pre-merge head reads entirely
    plausible, is what the guard's own message used to recommend, and fails exactly this.
    """
    root = MIGRATIONS.parents[3]
    for path, rule, commit in _merge_train_evidence():
        probe = subprocess.run(
            ["git", "grep", "-q", rule, commit, "--", "src/"], cwd=root, capture_output=True
        )
        assert probe.returncode == 0, (
            f"{path.name} publishes {rule} at {commit[:7]}, which does not contain it —"
            " repoint to the first commit on main that does, which is the merge commit"
        )
