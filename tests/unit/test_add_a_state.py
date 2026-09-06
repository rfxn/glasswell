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
from glasswell.seed.jurisdictions import CODES, JURISDICTIONS, NAMES, PREFIXES

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
PACKAGE_ROOT_FILES = (
    "absence.py",
    "identity.py",
    "lengths.py",
    "status_resolution.py",
    "units.py",
)

TWO_DIGIT_LITERAL = re.compile(r"""['"](\d{2})['"]""")
# Narrowed, never widened. The generic rule needs the quote immediately before the digits, so
# a two-digit alternation group -- `(25|33)[0-9]{8}` -- put a parenthesis there and walked past
# it. Measured over the four scanned trees, thirteen raw-string regex literals contain a
# two-digit run and every one of them is a quantifier or a hex class; none matches this.
ALTERNATION_GROUP = re.compile(r"\((?:\d{2}\|)+\d{2}\)")
# The anchored single-prefix shape beside it: `^05[0-9]{8}$` passes both the generic rule and
# the alternation arm, and the project already knows that shape exists because 045 carries it.
PREFIXED_API10 = re.compile(r"\d{2}(?:\[0-9\]|\\d)\{\d")
CODES_LITERAL = re.compile(r"""['"]([A-Z]{2})['"]""")
# Not scanned, and deliberately: a jurisdiction also appears lowercase inside a conformance
# rule id (`cr_tx_status_vocab_1`), and two STATUS_CLASSES rows cite one by family for the
# reason `rule_for_family` exists -- a supersession changes the id and must not be missed, and
# New Mexico's is already `_2`. Every row in that list already carries a `rule:` field citing a
# conformance rule, so citing a family is the R8-approved form rather than a way past this
# gate. Recorded here so the shape is a decision a reader can find, not one the scan walks
# past in silence (gate-seam N-1).
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


# The mart-module STATE_CODE exemption is gone rather than unmatched: the four modules that
# declared a prefix are shims now and the engine takes its prefix from the registration it
# loads, so there is no literal left for the exemption to cover and an exemption nothing
# matches is a hole waiting for something to fall through it.
PYTHON_EXEMPTIONS = (
    Exemption(
        "a mart's own jurisdiction registration",
        "The engine's profile rows and the four shims each declare which registration they"
        " refresh, and that declaration is the one place a code may be written down: every"
        " other fact about the jurisdiction is resolved from the row it names.",
        lambda path, line, value: (
            path.parent.name == "marts"
            and value in CODES
            and (
                re.fullmatch(rf'JURISDICTION_CODE(: str)? = "{value}"', line.strip()) is not None
                or (
                    path.name == "wells.py"
                    and (f'jurisdiction_code="{value}"' in line or f'"{value}"),' in line)
                )
            )
        ),
    ),
    Exemption(
        "marts/neighbors.py's output partition",
        "The neighbours mart's own output partition, which sits inside the derivation address"
        " beside params_hash. Rekeying it moves marts.nd_neighbors, whose rows carry a"
        " derivation_id and whose figures are served with handles.",
        lambda path, line, value: (
            path.name == "neighbors.py" and "partition" in line
        ),
    ),
    Exemption(
        "status/collector.py's per-jurisdiction presentation record",
        "Per-jurisdiction prose rather than a mapping decision: the sentence an operator reads"
        " beside a completions count. The registry spec left it as a declaration, and a fifth"
        " jurisdiction adds its row here in the same phase that registers it.",
        lambda path, line, value: (
            path.name == "collector.py" and "_CompletionsPresentation" in line
        ),
    ),
    Exemption(
        "marts/cumulatives.py's withholding map",
        "WITHHOLDING_BY_PREFIX and STATE_API_PREFIXES both derive from it and both are"
        " derivation params, so a flat (source_id, class) tuple rebuilds neither at the same"
        " value: params_hash moves and with it the mart.refresh id for"
        " marts.well_withholding, whose figures are served with handles. Rekeying a served"
        " address for a naming property is the wrong trade.",
        lambda path, line, value: (
            path.name == "cumulatives.py" and value in CODES
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


# A layer id that spells a jurisdiction code is a jurisdiction literal, and the two-digit rule
# cannot see it: `co-wells` carries no prefix, no name and no alternation group. North Dakota's
# `wells` is deliberately not in this set -- it predates the per-jurisdiction spelling, spells no
# code, and every saved permalink froze it.
JURISDICTION_LAYER_IDS = frozenset(
    str(value)
    for row in JURISDICTIONS
    for column in ("wells_layer_id", "wells_tile_layer_id")
    if (value := row.get(column)) is not None
    and str(row["jurisdiction_code"]).lower() in str(value).lower()
)


def _exempt(exemptions, path: Path, line: str, value: str) -> Exemption | None:
    return next((item for item in exemptions if item.matches(path, line, value)), None)


def scan_python(files: list[Path]) -> list[str]:
    """Any two-digit string literal, whatever its value: an unregistered one is a new
    jurisdiction slipping in, a registered one is a decision that belongs in a row. Plus a
    registered code, and the two regex shapes a quoted-literal rule cannot see."""
    found = []
    for path in files:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for pattern in (TWO_DIGIT_LITERAL, CODES_LITERAL):
                for match in pattern.finditer(line):
                    if match.group(1) not in CODES and pattern is CODES_LITERAL:
                        continue
                    if _exempt(PYTHON_EXEMPTIONS, path, line, match.group(1)) is None:
                        found.append(f"{_named(path)}:{number}: {match.group(0)}")
            for pattern in (ALTERNATION_GROUP, PREFIXED_API10):
                for match in pattern.finditer(line):
                    if _exempt(PYTHON_EXEMPTIONS, path, line, match.group(0)) is None:
                        found.append(f"{_named(path)}:{number}: {match.group(0)}")
    return found


def scan_web(files: list[Path]) -> list[str]:
    """Comments stripped first: prose naming a state is documentation, not a mapping."""
    found = []
    for path in files:
        body = TS_COMMENT.sub("", path.read_text(encoding="utf-8"))
        for number, line in enumerate(body.splitlines(), 1):
            for pattern in (TWO_DIGIT_LITERAL, CODES_LITERAL):
                for match in pattern.finditer(line):
                    if match.group(1) not in CODES and pattern is CODES_LITERAL:
                        continue
                    if _exempt(WEB_EXEMPTIONS, path, line, match.group(1)) is None:
                        found.append(f"{_named(path)}:{number}: {match.group(0)}")
            for name in NAMES:
                if name in line and _exempt(WEB_EXEMPTIONS, path, line, name) is None:
                    found.append(f"{_named(path)}:{number}: {name!r}")
            for layer_id in JURISDICTION_LAYER_IDS:
                if f'"{layer_id}"' in line and _exempt(
                    WEB_EXEMPTIONS, path, line, layer_id
                ) is None:
                    found.append(f"{_named(path)}:{number}: {layer_id!r}")
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


def test_the_layer_id_rule_covers_every_registration_but_the_irregular_one() -> None:
    """The set the web scan reads, checked so it cannot quietly go empty.

    A jurisdiction-scoped layer id is the shape a two-digit scan is blind to, and it is the one
    the wells family multiplies: two ids per registration, in a roster that grows by a row per
    state. North Dakota's `wells` is the exception and stays out by spelling no code.
    """
    assert len(JURISDICTION_LAYER_IDS) >= 2 * (len(CODES) - 1)
    assert "wells" not in JURISDICTION_LAYER_IDS
    assert {"co-wells", "co_wells"} <= JURISDICTION_LAYER_IDS


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
# Wyoming, because Colorado is registered now and a fixture planting a registered prefix
# proves the opposite of what it is written for: the scan would refuse it for being a prefix
# at all rather than for being an unregistered one, and the arm that reads the registry would
# never be exercised. 49 is Wyoming's API state code and the next of the Rockies sequence,
# so the fixture is the shape the next state actually arrives in.
PLANTED = (
    ("python", 'WYOMING_RULES = {"49": "cr_wy_status_vocab_1"}\n'),
    ("web", 'const WY = { "49": "Wyoming" };\n'),
    ("migration", "check (left(api10, 2) = '49')\n"),
    # The alternation-group shape: a quoted-literal rule needs the quote immediately before
    # the digits, and the parenthesis walks past it.
    ("python", 'PATTERN = re.compile(r"(49|33)[0-9]{8}")\n'),
    # The anchored single-prefix shape, which passes both the generic rule and the alternation
    # arm. 045 carries this shape as applied history, so the project knows it exists.
    ("python", 'PATTERN = re.compile(r"^49[0-9]{8}$")\n'),
)

# The `CODES` arm's own shapes, kept apart from the prefix fixtures above because it answers a
# different question: not "is a new jurisdiction slipping in" but "is a decision about a
# registered one written as a code here instead of resolved from its row". Scoped to registered
# codes deliberately -- an unrestricted two-uppercase rule matches the NDIC well-type codes AI,
# GI and WI, a link relation and two unrelated keys, and would cost five exemptions to buy one.
PLANTED_CODES = (
    ("python", 'PRESENTATION = {"MT": _Presentation(scope="Montana")}\n'),
    ("web", 'const RULES = { rule: jurisdictionRule("MT", "status_vocabulary") };\n'),
)

# Every raw-string regex literal in the scanned trees that contains a two-digit run and is a
# quantifier or a hex class rather than a jurisdiction. Neither new arm may match one.
QUANTIFIER_LITERALS = (
    r'API10_PATTERN = r"^[0-9]{10}$"',
    r'HANDLE = re.compile(r"^drv_[0-9a-z]{20}$")',
    r'_SHA256 = re.compile(r"^[0-9a-f]{64}$")',
    r'_KEY = re.compile(r"^[a-z0-9_]{1,64}$")',
    r'_COLOUR = re.compile(r"^#[0-9A-F]{6}$")',
    r'_TOKEN = re.compile(r"[A-Za-z0-9]{12,}")',
    r'_ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")',
)


@pytest.mark.parametrize(
    ("tree", "planted"),
    PLANTED,
    ids=[f"{item[0]}-{index}" for index, item in enumerate(PLANTED)],
)
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


@pytest.mark.parametrize("literal", QUANTIFIER_LITERALS)
def test_neither_new_arm_matches_a_quantifier_or_a_hex_class(
    tmp_path: Path, literal: str
) -> None:
    """M-8's whole point: the gate is narrowed, not widened. A rule that reddened on
    `{10}` or `[0-9a-f]{64}` would be paid for in exemptions, and an exemption is a hole."""
    assert ALTERNATION_GROUP.search(literal) is None, literal
    assert PREFIXED_API10.search(literal) is None, literal

    planted = tmp_path / "quantifiers.py"
    planted.write_text(literal + "\n", encoding="utf-8")
    assert scan_python([planted]) == []


def test_the_exemption_count_is_stated_as_a_number_and_not_as_an_absence() -> None:
    """"No new exemptions" is unfalsifiable. Eight is not: six Python and two web, each named
    above with its reason and each proven load-bearing by the test before this one."""
    assert len(PYTHON_EXEMPTIONS) == 6
    assert len(WEB_EXEMPTIONS) == 2
    assert len(PYTHON_EXEMPTIONS) + len(WEB_EXEMPTIONS) == 8


@pytest.mark.parametrize(
    ("tree", "planted"), PLANTED_CODES, ids=[item[0] for item in PLANTED_CODES]
)
def test_the_scan_sees_a_registered_code_used_as_a_key(
    tmp_path: Path, tree: str, planted: str
) -> None:
    """The four sites §1.5 inventories are all this shape: a per-jurisdiction dict keyed on a
    code, with no two-digit literal and no jurisdiction name anywhere on the line."""
    planted_file = tmp_path / ("montana.py" if tree == "python" else "montana.ts")
    planted_file.write_text(planted, encoding="utf-8")

    assert (scan_python if tree == "python" else scan_web)([planted_file])


def test_what_the_migration_scan_refuses_is_the_reach_into_an_api10_not_the_prefix(
    tmp_path: Path,
) -> None:
    """The seam, stated as a difference rather than as an absence.

    The scan's whole claim is that it refuses a jurisdiction being written into code, not that
    it refuses two digits. Both halves have to be exercised or the rule is indistinguishable
    from one that bans the shape. So: a registered prefix and an unregistered one, on the same
    query against the registry, are **both** admitted -- neither reaches into an API-10 -- and
    the same two prefixes inside a `left(api10, 2)` are both refused. The arm that fires is the
    one that reaches, whichever prefix it names.
    """
    registered = sorted(PREFIXES)[0]
    unregistered = "select * from lineage.jurisdictions where identity_prefix = '49'\n"
    admitted = f"select * from lineage.jurisdictions where identity_prefix = '{registered}'\n"

    assert scan_migrations([_written(tmp_path, "099_registered.sql", admitted)]) == []
    assert scan_migrations([_written(tmp_path, "099_planted.sql", unregistered)]) == []
    assert scan_migrations([_written(tmp_path, "099_reach.sql", "left(api10, 2) = '49'\n")])
    assert scan_migrations(
        [_written(tmp_path, "099_reach_registered.sql", f"left(api10, 2) = '{registered}'\n")]
    )


def test_the_planted_state_is_one_the_registry_does_not_hold() -> None:
    """A fixture planting a registered prefix proves the opposite of what it is written for:
    the scan would refuse it for being a prefix at all, and the arm that reads the registry
    would never run. This is what makes the negative fixtures move when a state lands."""
    planted = {value for _tree, value in PLANTED}
    for prefix in PREFIXES:
        assert not any(f'"{prefix}"' in value or f"'{prefix}'" in value for value in planted), (
            f"the planted sixth state uses {prefix}, which the registry now holds"
        )
    for name in NAMES:
        assert not any(name in value for value in planted)


def _written(root: Path, name: str, body: str) -> Path:
    """A planted file outside the tree, in a directory pytest removes after the run."""
    path = root / name
    path.write_text(body, encoding="utf-8")
    return path
