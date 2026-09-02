"""Every operator entry point takes its DSN from the environment, and none needs it on argv.

A DSN on a command line is visible in `/proc` to every user on the box and lands in shell
history; `scripts/smoke.sh` states the same principle for the owner key, and the pipeline units
have carried a password-free socket DSN in `GLASSWELL_DSN` since they were written.

**The set is discovered, never counted.** It is `[project.scripts]` plus every module under
`ingest/` and `marts/` with a `main`, read from the tree at test time, so a module written
after this branch is covered by the same assertions without anybody remembering to add it --
which is exactly how the four modeling entry points and the context-repair doc were missed
before.
"""

from __future__ import annotations

import importlib
import re
import tomllib
from pathlib import Path

import psycopg
import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src"
MAIN = re.compile(r"^def main\(", re.MULTILINE)

# The one entry point that must never take a DSN, rather than one that merely need not. The
# scheduler unit's ExecStart is asserted DSN-free by the deploy gate, and a flag here would be
# an invitation to put one there.
NO_DSN_BY_DESIGN = {"glasswell.scheduler.cli"}
# The four shims pass their argv straight to the engine, so the flag they honour is its flag.
SHIMS = {
    "glasswell.marts.nd_wells",
    "glasswell.marts.tx_wells",
    "glasswell.marts.nm_wells",
    "glasswell.marts.mt_wells",
}


def discovered() -> tuple[tuple[str, str], ...]:
    """Every entry point, as (module, function). The console scripts name their own function;
    a module found by its `main` names that."""
    with (ROOT / "pyproject.toml").open("rb") as handle:
        scripts = tomllib.load(handle)["project"]["scripts"]
    entries = {tuple(target.split(":", 1)) for target in scripts.values()}
    for tree in ("ingest", "marts"):
        for path in sorted((SOURCE / "glasswell" / tree).glob("*.py")):
            if path.name == "__init__.py":
                continue
            if MAIN.search(path.read_text(encoding="utf-8")):
                entries.add((f"glasswell.{tree}.{path.stem}", "main"))
    return tuple(sorted(entries))


DISCOVERED = discovered()
MODULES = tuple(sorted({module for module, _function in DISCOVERED}))
TAKES_DSN = tuple(module for module in MODULES if module not in NO_DSN_BY_DESIGN | SHIMS)
CALLABLE_ENTRIES = tuple(
    entry for entry in DISCOVERED if entry[0] not in NO_DSN_BY_DESIGN | SHIMS
)


def source_of(module: str) -> str:
    return (SOURCE / (module.replace(".", "/") + ".py")).read_text(encoding="utf-8")


def test_the_discovery_finds_both_halves_of_the_set() -> None:
    """A walk that matched nothing would satisfy every assertion below by vacuity."""
    assert len(MODULES) > 20
    assert "glasswell.modeling.type_curve" in MODULES, "the [project.scripts] half"
    assert "glasswell.ingest.nm_ocd" in MODULES, "the module-with-a-main half"
    assert "glasswell.marts.counts" in MODULES, "a main added after this test was written"
    assert ("glasswell.api.bootstrap", "bootstrap_main") in DISCOVERED, "not every one is main"


@pytest.mark.parametrize("module", TAKES_DSN)
def test_no_entry_point_requires_a_dsn_on_its_command_line(module: str) -> None:
    text = source_of(module)

    assert '"--dsn", required=True' not in text
    assert "add_dsn_argument(parser)" in text or '"--dsn"' in text


@pytest.mark.parametrize("module", TAKES_DSN)
def test_every_entry_point_resolves_the_same_two_variables(module: str) -> None:
    """One resolver, so a third fallback is one edit rather than thirty."""
    text = source_of(module)

    assert "resolve_dsn" in text or "FALLBACK_DSN_ENV" in text, module


@pytest.mark.parametrize(("module", "function"), CALLABLE_ENTRIES)
def test_every_entry_point_still_accepts_the_flag(module: str, function: str) -> None:
    entry = getattr(importlib.import_module(module), function)

    with pytest.raises(SystemExit) as exit_info:
        entry(["--help"])
    assert exit_info.value.code == 0


def test_the_shims_hand_the_flag_to_the_engine_rather_than_declaring_their_own() -> None:
    for module in sorted(SHIMS):
        text = source_of(module)
        assert '"--dsn"' not in text, f"{module} declares a flag the engine already has"
        assert "engine_main" in text


def test_the_scheduler_takes_no_dsn_at_all() -> None:
    text = source_of("glasswell.scheduler.cli")

    assert '"--dsn"' not in text
    assert "GLASSWELL_DSN" in text, "it still has to read one from its unit's environment"


def test_a_missing_dsn_raises_one_error_naming_both_variables(monkeypatch) -> None:
    from glasswell.db.dsn import DSN_ENV, FALLBACK_DSN_ENV, resolve_dsn

    monkeypatch.delenv(DSN_ENV, raising=False)
    monkeypatch.delenv(FALLBACK_DSN_ENV, raising=False)

    with pytest.raises(SystemExit) as refusal:
        resolve_dsn(None)

    assert DSN_ENV in str(refusal.value)
    assert FALLBACK_DSN_ENV in str(refusal.value)


def test_the_fallback_order_is_the_flag_then_the_two_variables(monkeypatch) -> None:
    from glasswell.db.dsn import DSN_ENV, FALLBACK_DSN_ENV, resolve_dsn

    monkeypatch.setenv(FALLBACK_DSN_ENV, "postgresql:///from-database-url")
    assert resolve_dsn(None) == "postgresql:///from-database-url"

    monkeypatch.setenv(DSN_ENV, "postgresql:///from-glasswell-dsn")
    assert resolve_dsn(None) == "postgresql:///from-glasswell-dsn"
    assert resolve_dsn("postgresql:///from-the-flag") == "postgresql:///from-the-flag"


@pytest.mark.parametrize("module", TAKES_DSN)
def test_every_entry_point_reads_the_environment_when_the_flag_is_absent(
    module: str, monkeypatch
) -> None:
    """The behaviour, not the source: a main that parses its argv and never resolves would
    pass a text check and still refuse on the host."""
    # A unix socket directory that does not exist: local, instant, and no listener anywhere.
    monkeypatch.setenv("DATABASE_URL", "postgresql:///probe?host=/nonexistent-gw-probe")
    monkeypatch.delenv("GLASSWELL_DSN", raising=False)
    entry = importlib.import_module(module)
    source = source_of(module)
    if "add_dsn_argument(parser)" not in source:
        pytest.skip(f"{module} keeps its own default; its fallback is asserted above")

    # The parser is built inside main, so the resolution is observed through what fails
    # afterwards. Two outcomes are correct and one is not: psycopg refusing the unreachable
    # socket means the DSN resolved, and argparse exiting 2 means the parser refused a
    # different missing argument before the DSN was ever a question. Refusing *for want of a
    # DSN* is the failure this asserts against.
    with pytest.raises((SystemExit, psycopg.OperationalError)) as failure:
        entry.main([])
    assert "no database DSN" not in str(failure.value), module


DOCS = ROOT / "docs"
# Any language tag, not just bash: an unmatched opener desynchronises the pairing and
# every later block reads as prose.
FENCE = re.compile(r"^```[a-z]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
# A `\`-continued shell command, rejoined, so a property three lines below the invocation is
# read as part of it rather than as its own line.
CONTINUED = re.compile(r"\\\n\s*")
RUNS_GLASSWELL = re.compile(r"(glasswell/venv/bin/|\$VENV/bin/|-m\s+glasswell\.)")
NAMES_A_DSN = re.compile(
    r"--property=EnvironmentFile=-?/etc/glasswell/\S+|--setenv=(GLASSWELL_DSN|DATABASE_URL)="
)


def fenced_commands(text: str) -> list[str]:
    joined = []
    for block in FENCE.findall(text):
        joined.extend(CONTINUED.sub(" ", block).splitlines())
    return joined


def test_no_operator_document_passes_a_dsn_on_an_argument_list() -> None:
    """Proof 4. An argument list is readable in /proc and lands in shell history."""
    offenders = [
        f"{path.name}: {line.strip()}"
        for path in sorted(DOCS.glob("*.md"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if "--dsn" in line
    ]

    assert offenders == []


def test_every_systemd_run_of_a_glasswell_command_names_where_its_dsn_comes_from() -> None:
    """The other half of proof 4, and the half the deletion alone would satisfy.

    A transient unit gets PID 1's environment, not the operator's shell, so removing `--dsn`
    without naming an environment file or a `--setenv` leaves the command with no database at
    all -- which is how six procedures, one of them the 89-minute production promotion, would
    have exited on `no database DSN`.
    """
    silent = []
    for path in sorted(DOCS.glob("*.md")):
        for command in fenced_commands(path.read_text(encoding="utf-8")):
            if "systemd-run" not in command or not RUNS_GLASSWELL.search(command):
                continue
            if not NAMES_A_DSN.search(command):
                silent.append(f"{path.name}: {command.strip()[:90]}")

    assert silent == []


def test_the_systemd_run_walk_reaches_the_blocks_it_is_meant_to_judge() -> None:
    """A walker that matched nothing would satisfy the assertion above by vacuity."""
    found = [
        command
        for path in sorted(DOCS.glob("*.md"))
        for command in fenced_commands(path.read_text(encoding="utf-8"))
        if "systemd-run" in command and RUNS_GLASSWELL.search(command)
    ]

    assert len(found) >= 8, found


def test_every_preserve_env_names_a_variable_its_own_document_exports() -> None:
    """`sudo --preserve-env=X` carries nothing when nothing ever exported X."""
    unexported = []
    for path in sorted(DOCS.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for command in fenced_commands(text):
            for match in re.finditer(r"--preserve-env=([A-Z0-9_,]+)", command):
                for name in match.group(1).split(","):
                    if name in ("GLASSWELL_CODE_VERSION", "GLASSWELL_LOCKFILE_SHA256"):
                        continue  # sourced from code-version.env under `set -a`
                    if not re.search(rf"^export {name}=", text, re.MULTILINE):
                        unexported.append(f"{path.name}: {name}")

    assert unexported == []
