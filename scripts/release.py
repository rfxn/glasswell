#!/usr/bin/env python3
"""Cut a release: bump the odometer, fold the pending fragments, commit, annotate a tag.

    scripts/release.py --dry-run    # preflight verdict, the fold, the commit and the tag body
    scripts/release.py              # one increment: 0.20 -> 0.21 -> ... -> 0.99 -> 1.0
    scripts/release.py --major      # exceptional: jump to the next major (RELEASING.md §4)
    scripts/release.py --set 1.05   # exceptional: name the version outright

The version grammar is an odometer, not semver: MAJOR.NN, one increment per release, NN
rolling 0-99 into the next major. `VERSION` carries the owner literal (`1.01`) and is the
source of truth; pyproject carries the PEP 440 equivalent (`1.1`), because a release segment
with a leading zero is not canonical and packaging collapses it whatever this file writes.
The tag, the changelog heading and the header stamp all render the owner literal.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_BRANCH = "main"
UPSTREAM = "origin/main"
UNRELEASED = "## Unreleased"

# `X.0`, then `X.01`..`X.09`, then `X.10`..`X.99`. Nothing else is a version this project cut.
OWNER_LITERAL = re.compile(r"^(0|[1-9][0-9]*)\.(0|0[1-9]|[1-9][0-9])$")
PYPROJECT_VERSION = re.compile(r'^version = "[^"]*"$', re.MULTILINE)
# `anchor()` builds every anchor from this, so recognising one needs no second grammar.
ANCHOR_PREFIX = '<a id="v'
RELEASE_SURFACE_FILES = ("README.md", "STATUS.md", "ROADMAP.md", "llms.txt")

# A migration that registers conformance-rule publication evidence has to name the release the
# rule first shipped in — and the branch that writes it cannot know that number, because merge
# order decides it. So it writes these, and the integrator repoints them at the merge train.
# `lineage.conformance_rule_publications` is append-only, so a guessed tag that reaches a
# production migrate is a permanent false claim about when glasswell could know a rule. This is
# the assertion that stops one leaving in a tagged release rather than relying on memory.
MIGRATIONS_DIR = Path("src/glasswell/db/migrations")
PLACEHOLDER_EVIDENCE_TAG = "UNRELEASED"
PLACEHOLDER_EVIDENCE_COMMIT = "0" * 40


@dataclass(frozen=True, order=True)
class Version:
    major: int
    tick: int

    @classmethod
    def parse(cls, literal: str) -> Version:
        match = OWNER_LITERAL.match(literal.strip())
        if not match:
            raise ValueError(f"not a glasswell version: {literal!r} (expected MAJOR.NN)")
        return cls(int(match.group(1)), int(match.group(2)))

    @property
    def owner(self) -> str:
        """The literal every reader-facing surface renders: tag, heading, header stamp."""
        return f"{self.major}.0" if self.tick == 0 else f"{self.major}.{self.tick:02d}"

    @property
    def pep440(self) -> str:
        """What pyproject stores. `1.01` is not canonical PEP 440; `1.1` is the same release."""
        return f"{self.major}.{self.tick}"

    @property
    def tag(self) -> str:
        return f"v{self.owner}"

    def next(self, *, major: bool = False) -> Version:
        if major or self.tick == 99:
            return Version(self.major + 1, 0)
        return Version(self.major, self.tick + 1)


# The odometer starts here rather than at 0.0: `0.1.0` was the pre-scheme pyproject value and
# no release was ever cut from it, so the first tag is the owner's chosen entry point.
SEED = Version(0, 20)


def load_assembler(root: Path = ROOT):
    """changelog-assemble.py owns fragment discovery and the entry grammar; borrow both."""
    path = root / "scripts" / "changelog-assemble.py"
    spec = importlib.util.spec_from_file_location("changelog_assemble", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"{path}: cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    # No bytecode: importing by path writes scripts/__pycache__, and the precondition two
    # lines below is about to assert this tree is clean.
    written, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = written
    return module


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)}: {result.stderr.strip() or 'failed'}")
    # rstrip, not strip: `status --porcelain` opens each line with the two status columns, and
    # eating the leading space turns ` M Makefile` into `akefile` in the refusal message.
    return result.stdout.rstrip("\n")


def git_ok(root: Path, *args: str) -> bool:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    return result.returncode == 0


def read_version(root: Path = ROOT) -> Version | None:
    path = root / "VERSION"
    if not path.is_file():
        return None
    try:
        return Version.parse(path.read_text())
    except ValueError as bad:
        # A half-migrated tree still carrying the pre-scheme `0.1.0` meets this on its first
        # run, and this file's contract is to refuse in prose rather than raise (gate-rel F7).
        raise SystemExit(f"{path}: {bad}") from None


def preconditions(root: Path, fragments: list[Path], target: Version) -> list[str]:
    """Every reason this tree cannot be released, so one run reports all of them."""
    blockers: list[str] = []

    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if branch != RELEASE_BRANCH:
        blockers.append(
            f"on branch {branch!r}, not {RELEASE_BRANCH!r} — a tag on a topic branch names a "
            "commit the release line does not contain; merge first"
        )

    dirty = git(root, "status", "--porcelain").splitlines()
    if dirty:
        listed = ", ".join(line[3:] for line in dirty[:6])
        blockers.append(
            f"working tree is not clean ({len(dirty)} path(s): {listed}) — a release describes "
            "a commit, and an uncommitted file is in no commit"
        )

    if not fragments:
        blockers.append(
            "changelog.d holds no fragment — the tag body would be empty, and a release nobody "
            "can read the contents of is the thing this scheme exists to prevent"
        )

    if not git_ok(root, "rev-parse", "--verify", "--quiet", UPSTREAM):
        blockers.append(f"no {UPSTREAM} — cannot tell whether this tree is behind the remote")
    elif git(root, "rev-parse", "HEAD") != git(root, "rev-parse", UPSTREAM):
        ahead = git(root, "rev-list", "--count", f"{UPSTREAM}..HEAD")
        behind = git(root, "rev-list", "--count", f"HEAD..{UPSTREAM}")
        blockers.append(
            f"HEAD is {ahead} ahead of and {behind} behind {UPSTREAM} — push or pull first, or "
            "the tag names a commit the remote has never seen"
        )

    if git_ok(root, "rev-parse", "--verify", "--quiet", f"refs/tags/{target.tag}"):
        blockers.append(f"tag {target.tag} already exists — the odometer has already passed it")

    blockers += placeholder_evidence_blockers(root, target)

    return blockers


def placeholder_evidence_blockers(root: Path, target: Version) -> list[str]:
    """Refuse to cut a release while a migration still carries placeholder rule evidence."""
    directory = root / MIGRATIONS_DIR
    if not directory.is_dir():
        return []
    # The quoted SQL literals, not the bare words. A bare-word scan matched the migration's own
    # header prose, so a correctly repointed file went on refusing and nothing in the repository
    # could cut a tag; and a bare forty-zero run is a substring of any longer all-zero digest.
    literals = (f"'{PLACEHOLDER_EVIDENCE_TAG}'", f"'{PLACEHOLDER_EVIDENCE_COMMIT}'")
    pending = sorted(
        path.name
        for path in directory.glob("*.sql")
        if any(literal in path.read_text(encoding="utf-8") for literal in literals)
    )
    if not pending:
        return []
    listed = ", ".join(pending)
    return [
        f"{len(pending)} migration(s) still carry {PLACEHOLDER_EVIDENCE_TAG} publication "
        f"evidence ({listed}) — repoint evidence_tag to {target.tag} and evidence_commit to "
        "the main head the rules were written against before cutting. "
        "lineage.conformance_rule_publications is append-only, so a placeholder that reaches a "
        "production migrate is a permanent false claim about when the rule was published"
    ]


def anchor(version: Version) -> str:
    """An explicit id: GitHub's slug of the heading moves the moment the date does."""
    return f'{ANCHOR_PREFIX}{version.owner}"></a>'


def collect_entries(assembler, fragments: list[Path]) -> tuple[list[str], list[str]]:
    """Read every fragment through the shared grammar, one blocker per refusal.

    The refusal is a blocker rather than an exception so a run still reports every reason at
    once — and so a bad fragment stops the release rather than the build after it (gate-rel B1).
    """
    entries: list[str] = []
    blockers: list[str] = []
    for fragment in fragments:
        try:
            entries.extend(assembler.read_entries(fragment).splitlines())
        except SystemExit as refusal:
            blockers.append(str(refusal))
    return entries, blockers


def render_blockers(renderer, folded: str, changelog: Path) -> list[str]:
    """The page's own parser and renderer over the candidate document, before any write.

    gate-rel B1: the fold used to be checked one line per fragment, so `make release` could cut
    a tag for a CHANGELOG.md the page would refuse at the next build. This refuses for exactly
    that reason, in exactly those words, before VERSION, CHANGELOG.md, the commit or the tag is
    touched.
    """
    try:
        renderer.render_html(renderer.parse_text(folded, changelog), changelog)
    except SystemExit as refusal:
        return [f"the folded CHANGELOG.md would not render — {refusal}"]
    return []


def fold(changelog: str, entries: list[str], version: Version, today: str) -> str:
    """Open a version section under `## Unreleased` and move everything pending into it."""
    lines = changelog.splitlines()
    try:
        start = lines.index(UNRELEASED)
    except ValueError:
        raise SystemExit(f"CHANGELOG.md: no {UNRELEASED!r} heading") from None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    # The previous version's anchor sits immediately above its own heading and belongs to that
    # section. Left inside the pending slice it is dragged into the new one, which parses but
    # opens a blank line between an anchor and the heading it names (gate-rel N1).
    if end > start + 1 and lines[end - 1].startswith(ANCHOR_PREFIX):
        end -= 1

    pending = lines[start + 1 : end]
    while pending and not pending[0].strip():
        pending.pop(0)
    while pending and not pending[-1].strip():
        pending.pop()

    block = ["", anchor(version), f"## {version.tag} — {today}", "", *entries]
    if pending:
        block += ["", *pending]
    lines[start + 1 : end] = [*block, ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def commit_message(version: Version, entries: list[str]) -> str:
    return f"Release {version.tag}\n\n" + "\n".join(entries) + "\n"


def tag_message(version: Version, entries: list[str], today: str) -> str:
    return f"glasswell {version.tag} — {today}\n\n" + "\n".join(entries) + "\n"


def bump_pyproject(text: str, version: Version) -> str:
    replaced, count = PYPROJECT_VERSION.subn(f'version = "{version.pep440}"', text, count=1)
    if count != 1:
        raise SystemExit('pyproject.toml: no `version = "..."` line to bump')
    return replaced


def _replace_one(
    text: str,
    pattern: str,
    replacement: str,
    path: Path,
    marker: str,
    *,
    flags: int = 0,
) -> tuple[str, list[str]]:
    expression = re.compile(pattern, flags)
    matches = list(expression.finditer(text))
    if len(matches) == 1:
        return expression.sub(replacement, text, count=1), []
    return text, [f"{path.name}: expected exactly one {marker}; found {len(matches)}"]


def tagged_release_count(root: Path) -> int:
    """Count only tags that belong to this project's odometer grammar."""
    count = 0
    for tag in git(root, "tag", "--list", "v*").splitlines():
        try:
            Version.parse(tag.removeprefix("v"))
        except ValueError:
            continue
        count += 1
    return count


def sync_release_surfaces(
    root: Path, current: Version, target: Version, today: str
) -> tuple[dict[Path, str], list[str]]:
    """Render the duplicated release facts, refusing ambiguous or partial collateral."""
    paths = [root / name for name in RELEASE_SURFACE_FILES]
    present = [path for path in paths if path.is_file()]
    if not present:
        return {}, []
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        return {}, [f"release collateral is incomplete; missing {', '.join(missing)}"]

    release_count = tagged_release_count(root) + 1
    updates: dict[Path, str] = {}
    blockers: list[str] = []

    readme = root / "README.md"
    text = readme.read_text()
    text, refusals = _replace_one(
        text,
        re.escape(f"release-{current.tag}-"),
        f"release-{target.tag}-",
        readme,
        "release badge URL",
    )
    blockers += refusals
    text, refusals = _replace_one(
        text,
        re.escape(f'alt="Release: {current.tag}"'),
        f'alt="Release: {target.tag}"',
        readme,
        "release badge label",
    )
    blockers += refusals
    updates[readme] = text

    status = root / "STATUS.md"
    text = status.read_text()
    text, refusals = _replace_one(
        text,
        rf"(?m)^Reconciled on \*\*\d{{4}}-\d{{2}}-\d{{2}}\*\* against the "
        rf"{re.escape(current.tag)} release line, the checked-in OpenAPI$",
        f"Reconciled on **{today}** against the {target.tag} release line, the checked-in "
        "OpenAPI",
        status,
        "current-status release preamble",
    )
    blockers += refusals
    text, refusals = _replace_one(
        text,
        rf"(?m)^- \*\*Release line:\*\* \d+ tagged releases, (v\d+\.\d+) through "
        rf"{re.escape(current.tag)}, cut (\d{{4}}-\d{{2}}-\d{{2}}) through\n  "
        r"\d{4}-\d{2}-\d{2}\.$",
        rf"- **Release line:** {release_count} tagged releases, \1 through {target.tag}, cut "
        rf"\2 through\n  {today}.",
        status,
        "shipped release-line ledger",
    )
    blockers += refusals
    updates[status] = text

    roadmap = root / "ROADMAP.md"
    text = roadmap.read_text()
    text, refusals = _replace_one(
        text,
        rf"(?m)^\d+ tagged releases, (v\d+\.\d+) through {re.escape(current.tag)}, cut from "
        r"(\d{4}-\d{2}-\d{2}) through \d{4}-\d{2}-\d{2}, run$",
        rf"{release_count} tagged releases, \1 through {target.tag}, cut from \2 through "
        f"{today}, run",
        roadmap,
        "roadmap release ledger",
    )
    blockers += refusals
    updates[roadmap] = text

    llms = root / "llms.txt"
    text = llms.read_text()
    text, refusals = _replace_one(
        text,
        re.escape(f"**Status: in build, release line {current.tag}.**"),
        f"**Status: in build, release line {target.tag}.**",
        llms,
        "machine-readable release status",
    )
    blockers += refusals
    updates[llms] = text

    if blockers:
        return {}, blockers
    return updates, []


def section(folded: str, version: Version) -> str:
    """The version's own slice of the folded changelog, anchor line included."""
    start = folded.index(anchor(version))
    # Past the heading line: it is itself a `## `, so searching from the anchor finds it.
    heading = folded.index(f"## {version.tag} — ", start) + len(f"## {version.tag} — ")
    end = folded.find("\n## ", heading)
    return folded[start : end if end != -1 else len(folded)]


def _print_blockers(blockers: list[str], lead: str, wrap: str, stream=None) -> None:
    """A `Refused` carries the offending line under its message; keep it readable.

    `stream=None` rather than `sys.stdout`: a default is bound once at import, and the caller
    may have replaced the stream since.
    """
    stream = stream or sys.stdout
    for blocker in blockers:
        head, *rest = blocker.splitlines()
        print(f"{lead}{head}", file=stream)
        for line in rest:
            print(f"{wrap}{line}", file=stream)


def _print_dry_run(
    root: Path,
    target: Version,
    current: Version | None,
    fragments: list[Path],
    entries: list[str],
    folded: str,
    blockers: list[str],
    today: str,
) -> None:
    previous = current.owner if current else "(none — seeding the odometer)"
    print(f"=== dry run — would cut {target.tag} on {today} ===\n")
    print(f"version    {previous} -> {target.owner}")
    print(f"pyproject  {target.pep440}    tag  {target.tag}    anchor  {anchor(target)}\n")

    print("preflight")
    _print_blockers(blockers, "  BLOCK  ", "         ")
    if not blockers:
        print("  ok     clean tree, on main, level with the remote, fragments that render")
    print()

    print(f"fragments ({len(fragments)}, folded in filename order)")
    for fragment in fragments:
        tally = sum(1 for line in fragment.read_text().splitlines() if line.startswith("- ["))
        print(f"  {fragment.relative_to(root)}  ({tally} entries)")
    print()

    slice_ = section(folded, target).splitlines()
    head = next((i for i, line in enumerate(slice_) if line.startswith("### ")), len(slice_))
    print(f"--- CHANGELOG.md § {target.tag} — the release's own entries ---")
    print("\n".join(slice_[:head]).rstrip())
    moved = [line for line in slice_[head:] if line.startswith("### ")]
    print(f"\n--- and {len(moved)} dated section(s) moved beneath it ---")
    for line in moved:
        print(f"  {line}")
    print(f"\n--- commit message ---\n{commit_message(target, entries)}")
    print(f"--- tag {target.tag} (annotated) ---\n{tag_message(target, entries, today)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print everything, write nothing")
    parser.add_argument("--check", action="store_true", help="preflight only; exit 1 if blocked")
    parser.add_argument("--major", action="store_true", help="jump to the next major (§4)")
    parser.add_argument("--set", dest="explicit", default="", help="name the version outright")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--date", default=date.today().isoformat())
    arguments = parser.parse_args(argv)
    root: Path = arguments.root

    if arguments.explicit and arguments.major:
        raise SystemExit("--set and --major name two different versions; pass one")

    current = read_version(root)
    if arguments.explicit:
        try:
            target = Version.parse(arguments.explicit)
        except ValueError as bad:
            raise SystemExit(f"--set: {bad}") from None
    elif current is None:
        target = SEED
    else:
        target = current.next(major=arguments.major)
    if current is not None and target <= current:
        raise SystemExit(
            f"{target.owner} does not follow {current.owner} — the odometer only turns forward"
        )

    assembler = load_assembler(root)
    fragments = assembler.pending_fragments(root / "changelog.d")
    blockers = preconditions(root, fragments, target)
    entries, refusals = collect_entries(assembler, fragments)
    blockers += refusals

    changelog = root / "CHANGELOG.md"
    pyproject = root / "pyproject.toml"
    folded = fold(changelog.read_text(), entries, target, arguments.date)
    bumped = bump_pyproject(pyproject.read_text(), target)
    # The last gate before anything is written: the page's own parser over the document this
    # release would commit. A tag must never name a changelog the next build cannot render.
    blockers += render_blockers(assembler.grammar(), folded, changelog)
    surface_updates: dict[Path, str] = {}
    if current is not None:
        surface_updates, surface_blockers = sync_release_surfaces(
            root, current, target, arguments.date
        )
        blockers += surface_blockers

    if arguments.check:
        if blockers:
            print(f"{target.tag} is blocked:", file=sys.stderr)
            _print_blockers(blockers, "  - ", "    ", stream=sys.stderr)
            return 1
        print(f"{target.tag} is ready: {len(fragments)} fragment(s), {len(entries)} entry line(s)")
        return 0

    if blockers and not arguments.dry_run:
        print(f"refusing to release {target.tag}:", file=sys.stderr)
        _print_blockers(blockers, "  - ", "    ", stream=sys.stderr)
        return 1

    if arguments.dry_run:
        _print_dry_run(root, target, current, fragments, entries, folded, blockers, arguments.date)
        return 0

    (root / "VERSION").write_text(f"{target.owner}\n")
    pyproject.write_text(bumped)
    changelog.write_text(folded)
    paths = ["VERSION", "pyproject.toml", "CHANGELOG.md"]
    for path, rendered in surface_updates.items():
        path.write_text(rendered)
        paths.append(str(path.relative_to(root)))
    for fragment in fragments:
        paths.append(str(fragment.relative_to(root)))
        fragment.unlink()

    git(root, "add", "--", *paths)
    git(root, "commit", "-m", commit_message(target, entries))
    git(root, "tag", "-a", target.tag, "-m", tag_message(target, entries, arguments.date))

    print(f"{target.tag} — {len(fragments)} fragment(s), {len(entries)} line(s) in the tag body")
    print(f"  VERSION    {target.owner}")
    print(f"  pyproject  {target.pep440}")
    print(f"  commit     {git(root, 'rev-parse', '--short', 'HEAD')}")
    print(f"  push with  git push origin {RELEASE_BRANCH} && git push origin {target.tag}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # dry-run output piped to head is normal usage
        sys.exit(0)
