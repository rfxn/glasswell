"""The tuning drop-in, the README that documents it, and the parser verify.sh reads it with.

Every `<setting> = <value>` line in the drop-in becomes a live assertion against the running
server (`infra/verify.sh:704-715`), and the drop-in reaches the host only through
`install.sh --with-postgres`, which a deploy never runs. So a setting that ships undocumented,
or one the README still lists as rejected, is a contradiction an operator resolves the wrong way
at the one moment it matters.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
DROPIN = ROOT / "infra" / "postgres" / "postgresql.conf.d" / "glasswell.conf"
README = ROOT / "infra" / "README.md"
SETTING = re.compile(r"^([a-z0-9_]+) = (.*)$")
BACKTICKED = re.compile(r"`([a-z0-9_]+)")


def settings() -> dict[str, str]:
    found: dict[str, str] = {}
    for line in DROPIN.read_text(encoding="utf-8").splitlines():
        match = SETTING.match(line)
        if match:
            found[match.group(1)] = match.group(2).split("#", 1)[0].strip()
    return found


def readme() -> str:
    return README.read_text(encoding="utf-8")


def test_every_setting_survives_the_parse_verify_reads_the_dropin_with() -> None:
    parsed = settings()

    assert parsed
    for name, value in parsed.items():
        # What `line="${line%%#*}"` and `read -r expected <<<"${line#* = }"` leave behind: an
        # empty or space-padded value is asserted against `show <setting>` and can never match.
        assert value, name
        assert value == value.strip(), name


def test_the_readme_counts_the_settings_the_dropin_actually_ships() -> None:
    stated = re.search(r"(\d+) settings sized", readme())

    assert stated is not None
    assert int(stated.group(1)) == len(settings())


def test_every_setting_the_dropin_ships_has_a_row_in_the_readme_table() -> None:
    documented: set[str] = set()
    for line in readme().splitlines():
        if line.startswith("| `"):
            documented.update(BACKTICKED.findall(line.split("|")[1]))

    assert set(settings()) <= documented


def test_nothing_the_dropin_ships_is_still_listed_as_considered_and_rejected() -> None:
    text = readme()
    start = text.index("**Considered and rejected**")
    paragraph = text[start : text.index("\n\n", start)]
    # The paragraph's subjects are the names outside the parentheses; a name inside one is a
    # comparison the rejection is argued against, and `effective_io_concurrency` is shipped.
    rejected = set(BACKTICKED.findall(re.sub(r"\([^)]*\)", "", paragraph)))

    assert rejected.isdisjoint(settings())


def test_the_deploy_runbook_says_how_a_reload_only_dropin_reaches_the_host() -> None:
    text = readme()
    step = text[text.index("# 5. Apply the Postgres tuning") : text.index("# 6. ")]

    assert "./install.sh --with-postgres" in step
    # deploy.sh:162 runs install.sh with no arguments and verify.sh compares the tree's drop-in
    # to the running server at the end, after install, marts and restarts have all happened --
    # so a drop-in shipped without this step is a red deploy that already deployed.
    assert "pg_reload_conf" in step
