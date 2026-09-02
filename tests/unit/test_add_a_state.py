"""The gate on a fifth jurisdiction: no tree may name one in code again.

Nineteen literals across the routers, the collector, two marts and the web bundle decided what
glasswell said about a jurisdiction. They are rows now, and this is what keeps them rows: a
two-digit API prefix, or a jurisdiction's name, appearing anywhere the serving path reads is a
refusal unless it is one of the exemptions named below, each with its reason.

The rule is positive and keyword-free, and that is the whole point (B-5). An earlier version
gated on a trigger word — `state`, `api10`, `prefix`, `left(` — and seventeen of the nineteen
literals it existed to catch sat in dict bodies with no such word on the line, so it was green
over the defect it was written for. Every rule here scans for the value itself.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import glasswell
from glasswell.seed.jurisdictions import CODES, NAMES, PREFIXES

pytestmark = pytest.mark.unit

SOURCE = Path(glasswell.__file__).parent
ROOT = SOURCE.parents[1]
WEB = ROOT / "web" / "src"
MIGRATIONS = SOURCE / "db" / "migrations"

# Migrations at or below this number are applied history: `migrate.py` refuses a hash change on
# an applied file, so 045's `^33[0-9]{8}$` is carried rather than edited (§1.2). Everything
# written after it is this track's contemporary or later, and has no such excuse.
APPLIED_HISTORY_CEILING = 71

PYTHON_TREES = ("marts", "api/routers", "status", "lineage", "scheduler")
# The package root as well as the four trees: `status_resolution.py` sat outside every one of
# them and carried `{"30": "cr_nm_wellhistory_status_vocab_2"}` for exactly that reason.
PACKAGE_ROOT_FILES = ("identity.py", "lengths.py", "status_resolution.py", "units.py")

TWO_DIGIT_LITERAL = re.compile(r"""['"](\d{2})['"]""")
API10_LITERAL = re.compile(r"\b(\d{2})[0-9]{8}\b")
PREFIX_PATTERN = re.compile(r"~ '\^(\d\d)")
TS_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
SQL_COMMENT = re.compile(r"--[^\n]*")


class Exemption:
    """A literal the scan is allowed to see, and why. Anything not here is a refusal."""

    def __init__(self, where: str, why: str, matches) -> None:
        self.where = where
        self.why = why
        self.matches = matches


PYTHON_EXEMPTIONS = (
    Exemption(
        "a mart module's own STATE_CODE",
        "One literal per module is the honest declaration of which regulator's data it parses"
        " or promotes; §5.2 step 6 requires it to equal a registered identity_prefix.",
        lambda path, line, value: (
            path.parent.name == "marts"
            and value in PREFIXES
            and re.fullmatch(rf'STATE_CODE(: str)? = "{value}"', line.strip()) is not None
        ),
    ),
    Exemption(
        "type_curves.py's quantile levels",
        "P10/P50/P90 are quantile levels, not state codes. The one exemption a keyword-free"
        " rule costs, and worth it — the alternative is the blind rule B-5 reopened.",
        lambda path, line, value: (
            path.name == "type_curves.py" and value in {"10", "50", "90"}
        ),
    ),
    Exemption(
        "the /v1/wells/facets request example",
        "Structurally required: an unexampled operation fails the OpenAPI snapshot gate, the"
        " naked-number walker calls every operation from its example, and _require_state"
        " refuses a call with no state.",
        lambda path, line, value: (
            path.name == "facets.py" and "request_example" in line
        ),
    ),
)

WEB_EXEMPTIONS = (
    Exemption(
        "page sizes and control bounds",
        "Numbers that happen to be two digits wide and mean something else entirely: an"
        " opacity floor, a page size, a list of page sizes one of which collides with"
        " Montana's prefix.",
        lambda path, line, value: (
            (path.name == "layer-panel.ts" and "opacity" in line)
            or (path.name == "wells-by.ts" and ("TOPS" in line or "DEFAULTS" in line))
            or (path.name == "query.ts" and "PAGE" in line)
        ),
    ),
    Exemption(
        "a jurisdiction-scoped layer's own label, and measured prose",
        "A row for the PLSS grid or the Montana well paths declares the extent it covers, the"
        " same honest declaration a mart module's STATE_CODE makes; and a subtitle that"
        " reports what was measured is prose, not a mapping. The rows this track collapsed are"
        " the identifying fields of the `family: \"wells\"` rows, and those carry no name.",
        lambda path, line, value: (
            path.name == "registry.ts"
            and not (
                re.match(r"\s*(familyLabel|label):", line)
                and 'family: "wells"' in _registry_block(path, line)
            )
        ),
    ),
)


def _registry_block(path: Path, line: str) -> str:
    """The registry row a line sits in, so a Wells-family row is judged apart from its
    neighbours. The same split `tests/e2e/chrome-fold.mjs` parses the file with."""
    for block in path.read_text(encoding="utf-8").split("\n  {\n"):
        if line in block:
            return block
    return ""


def python_files() -> list[Path]:
    scanned = [
        path
        for tree in PYTHON_TREES
        for path in (SOURCE / tree).glob("*.py")
        if path.name != "__init__.py"
    ]
    # Named rather than globbed: a new module at the package root should have to be looked at
    # and added here, not silently inherit a scan somebody else argued for.
    resident = {path.name for path in SOURCE.glob("*.py")} - {"__init__.py"}
    assert resident == set(PACKAGE_ROOT_FILES), (
        f"package root modules changed: {sorted(resident)} — add them to PACKAGE_ROOT_FILES"
    )
    return sorted(scanned + [SOURCE / name for name in PACKAGE_ROOT_FILES])


def web_files() -> list[Path]:
    return sorted(
        path
        for path in WEB.rglob("*.ts")
        # Fixtures and harness surfaces are test data that happens not to be named `.test.ts`;
        # the generated module is the registry itself, rendered.
        if not path.name.endswith(".test.ts")
        and path.name not in {"fixtures.ts", "jurisdictions.generated.ts"}
        and "test" not in path.relative_to(WEB).parts
    )


def recent_migrations() -> list[Path]:
    return sorted(
        path
        for path in MIGRATIONS.glob("*.sql")
        if int(path.name[:3]) > APPLIED_HISTORY_CEILING
    )


def _named(path: Path) -> str:
    """Repo-relative where possible; a planted fixture lives outside the tree."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return path.name


def _exempt(exemptions, path: Path, line: str, value: str) -> Exemption | None:
    return next((item for item in exemptions if item.matches(path, line, value)), None)


def scan_python(files: list[Path]) -> list[str]:
    """Any two-digit string literal, whatever its value: an unregistered one is a new
    jurisdiction slipping in, a registered one is a decision that belongs in a row."""
    found = []
    for path in files:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for match in TWO_DIGIT_LITERAL.finditer(line):
                if _exempt(PYTHON_EXEMPTIONS, path, line, match.group(1)) is None:
                    found.append(f"{_named(path)}:{number}: {match.group(0)}")
    return found


def scan_web(files: list[Path]) -> list[str]:
    """Comments stripped first: prose naming a state is documentation, not a mapping."""
    found = []
    for path in files:
        body = TS_COMMENT.sub("", path.read_text(encoding="utf-8"))
        for number, line in enumerate(body.splitlines(), 1):
            for match in TWO_DIGIT_LITERAL.finditer(line):
                if _exempt(WEB_EXEMPTIONS, path, line, match.group(1)) is None:
                    found.append(f"{_named(path)}:{number}: {match.group(0)}")
            for name in NAMES:
                if name in line and _exempt(WEB_EXEMPTIONS, path, line, name) is None:
                    found.append(f"{_named(path)}:{number}: {name!r}")
    return found


def scan_migrations(files: list[Path]) -> list[str]:
    """An API-10 literal or an anchored prefix pattern whose leading pair is unregistered, and
    any two-digit literal on a line that reaches into an API-10."""
    found = []
    for path in files:
        body = SQL_COMMENT.sub("", path.read_text(encoding="utf-8"))
        for number, line in enumerate(body.splitlines(), 1):
            for pattern in (API10_LITERAL, PREFIX_PATTERN):
                for match in pattern.finditer(line):
                    if match.group(1) not in PREFIXES:
                        found.append(f"{_named(path)}:{number}: {match.group(0)}")
            if "api10" in line or "left(" in line:
                for match in TWO_DIGIT_LITERAL.finditer(line):
                    found.append(f"{_named(path)}:{number}: {match.group(0)}")
    return found


def test_no_python_serving_module_names_a_jurisdiction() -> None:
    assert scan_python(python_files()) == []


def test_no_web_module_names_a_jurisdiction() -> None:
    assert scan_web(web_files()) == []


def test_no_migration_written_after_the_registry_hardcodes_a_prefix() -> None:
    assert recent_migrations(), "no migration is in scope; this gate would be vacuous"
    assert scan_migrations(recent_migrations()) == []


def test_every_exemption_is_load_bearing_and_says_why() -> None:
    """An exemption nothing matches is a hole waiting for something to fall through it."""
    for exemptions, files, scan in (
        (PYTHON_EXEMPTIONS, python_files(), scan_python),
        (WEB_EXEMPTIONS, web_files(), scan_web),
    ):
        for exemption in exemptions:
            assert len(exemption.why) > 40, exemption.where
            others = tuple(item for item in exemptions if item is not exemption)
            saved = exemptions
            try:
                globals()[
                    "PYTHON_EXEMPTIONS" if scan is scan_python else "WEB_EXEMPTIONS"
                ] = others
                assert scan(files) != [], f"nothing matches the {exemption.where} exemption"
            finally:
                globals()[
                    "PYTHON_EXEMPTIONS" if scan is scan_python else "WEB_EXEMPTIONS"
                ] = saved


# The negative fixtures, drawn from shapes the rules do NOT name (§5.1 rev 3). A fixture that
# carries the rule's own trigger proves only that the rule can see itself.
PLANTED = (
    ("python", 'COLORADO_RULES = {"05": "cr_co_status_vocab_1"}\n'),
    ("web", 'const CO = { "05": "Colorado" };\n'),
    ("migration", "check (left(api10, 2) = '05')\n"),
)


@pytest.mark.parametrize(("tree", "planted"), PLANTED, ids=[item[0] for item in PLANTED])
def test_the_scan_sees_a_new_prefix_in_every_tree(tmp_path: Path, tree: str, planted: str) -> None:
    """A dict body with no trigger word, an object literal with none, and a `left(api10, 2)`
    check that matches neither the API-10 nor the anchored-pattern form."""
    if tree == "python":
        planted_file = tmp_path / "colorado.py"
        planted_file.write_text(planted, encoding="utf-8")
        assert scan_python([planted_file])
    elif tree == "web":
        planted_file = tmp_path / "colorado.ts"
        planted_file.write_text(planted, encoding="utf-8")
        assert scan_web([planted_file])
    else:
        planted_file = tmp_path / "099_colorado.sql"
        planted_file.write_text(planted, encoding="utf-8")
        assert scan_migrations([planted_file])


def test_the_allowlist_is_the_registry_and_not_a_second_copy_of_it() -> None:
    """P5's whole gate rests on PREFIXES and NAMES; restated by hand they would drift."""
    assert PREFIXES
    assert NAMES
    assert CODES
    assert all(len(prefix) == 2 and prefix.isdigit() for prefix in PREFIXES)
