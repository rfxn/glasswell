"""One API-10, three loaders: the spine agrees because one rule row decides (R8).

FracFocus, the ND MPR and the ND directional survey each read their own identity row here,
never a literal retyped in this file, so a disagreement between the rows fails the test.
"""

from __future__ import annotations

import polars as pl
import pytest

from glasswell.identity import api10_identity
from glasswell.ingest.fracfocus import IDENTITY_FAMILY as FF_IDENTITY_FAMILY
from glasswell.ingest.nd_gis import _SURVEYS_SCHEMA, SURVEY_IDENTITY_FAMILY, keyed_stations
from glasswell.ingest.nd_mpr import IDENTITY_FAMILY as MPR_IDENTITY_FAMILY
from glasswell.ingest.nd_mpr import _typed_frame
from glasswell.lineage.conformance import active_rules, rule_for_family
from glasswell.lineage.errors import RuleSpecError
from glasswell.lineage.models import ConformanceRule
from glasswell.seed.conformance_fracfocus import EFFECTIVE_FROM as FF_EFFECTIVE_FROM
from glasswell.seed.conformance_fracfocus import FRACFOCUS_RULES
from glasswell.seed.conformance_nd import EFFECTIVE_FROM as ND_EFFECTIVE_FROM
from glasswell.seed.conformance_nd import ND_RULES

BARE = "33053039010000"
DASHED = "33-053-03901-00-00"
SPACED = "33 053 03901 00 00"
API10 = "3305303901"
# Values whose non-digit characters are annotation, not a published separator. Deleting every
# non-digit keyed all three onto a real well; declaring the separator set refuses them.
ANNOTATED = ("API 33053039010000", "33053039010000 (amended)", "33X053X03901X00X00")


def _hydrate(seeded: dict, *, seed_epoch) -> ConformanceRule:
    """The seeded row as the loader will read it back, so no spec is retyped in this file."""
    rule_id = str(seeded["rule_id"])
    fields = {key: value for key, value in seeded.items() if key != "effective_from"}
    fields.setdefault("rule_family", rule_id.rsplit("_", 1)[0])
    return ConformanceRule(
        effective_from=seeded.get("effective_from", seed_epoch),
        **fields,  # type: ignore[arg-type]
    )


def _active(seeds, seed_epoch, family: str) -> ConformanceRule:
    return rule_for_family(
        active_rules([_hydrate(seed, seed_epoch=seed_epoch) for seed in seeds]), family
    )


def fracfocus_rule() -> ConformanceRule:
    return _active(FRACFOCUS_RULES, FF_EFFECTIVE_FROM, FF_IDENTITY_FAMILY)


def mpr_rule() -> ConformanceRule:
    return _active(ND_RULES, ND_EFFECTIVE_FROM, MPR_IDENTITY_FAMILY)


def survey_rule() -> ConformanceRule:
    return _active(ND_RULES, ND_EFFECTIVE_FROM, SURVEY_IDENTITY_FAMILY)


def survey_api10(value: str | None) -> str | None:
    """The ND GIS path, driven through the loader rather than through the helper."""
    row = dict.fromkeys(_SURVEYS_SCHEMA)
    row["source_row_ordinal"] = 1
    row["api_wellno"] = value
    keyed, _ = keyed_stations(pl.DataFrame([row], schema=_SURVEYS_SCHEMA), survey_rule())
    return keyed[0]["api10"] if keyed else None


def mpr_api10(value: str | None) -> str | None:
    """The ND MPR path, driven through _typed_frame so the rule lookup is exercised too."""
    staged = pl.DataFrame(
        {"api_wellno": [value], "report_date": ["46082"], "days": ["31"], "oil": ["259"]}
    )
    typed = _typed_frame(staged, rules=[mpr_rule(), _month_rule()], measures=["oil"])
    return typed["api10"].to_list()[0]


def _month_rule() -> ConformanceRule:
    return _hydrate(
        next(rule for rule in ND_RULES if rule["rule_id"] == "cr_nd_month_convention_1"),
        seed_epoch=ND_EFFECTIVE_FROM,
    )


def fracfocus_api10(value: str | None) -> str | None:
    return api10_identity(fracfocus_rule()).normalize(value)


PATHS = {
    "fracfocus": fracfocus_api10,
    "nd_mpr": mpr_api10,
    "nd_gis_surveys": survey_api10,
}


@pytest.mark.parametrize("path", sorted(PATHS))
@pytest.mark.parametrize("published", [BARE, DASHED, SPACED])
def test_the_three_loaders_read_one_api10_out_of_every_published_form(path, published):
    """The regression: DASHED keyed under FracFocus and quarantined under ND GIS."""
    assert PATHS[path](published) == API10


@pytest.mark.parametrize("path", sorted(PATHS))
@pytest.mark.parametrize("annotated", ANNOTATED)
def test_no_loader_builds_an_identity_out_of_annotation(path, annotated):
    assert PATHS[path](annotated) is None


@pytest.mark.parametrize("path", sorted(PATHS))
@pytest.mark.parametrize("value", ["", "   ", "3305303901", "330530390100000", None])
def test_a_value_that_is_not_a_full_api14_keys_nowhere(path, value):
    assert PATHS[path](value) is None


def test_every_identity_rule_declares_the_same_separator_set():
    """A join key cannot differ by source, so the rows have to agree, not just the code."""
    specs = [api10_identity(rule()) for rule in (fracfocus_rule, mpr_rule, survey_rule)]
    assert len({spec.separators for spec in specs}) == 1
    assert len({(spec.digits, spec.start, spec.stop) for spec in specs}) == 1


def test_a_rule_row_that_does_not_declare_its_separators_is_refused():
    silent = mpr_rule().model_copy(
        update={"spec": {"digits": 14, "api10_slice": [0, 10]}}
    )
    with pytest.raises(RuleSpecError, match="separators must be declared"):
        api10_identity(silent)


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ({"digits": 0, "api10_slice": [0, 10], "separators": []}, "positive integer"),
        ({"digits": 14, "api10_slice": [0], "separators": []}, "start, stop"),
        ({"digits": 14, "api10_slice": [0, 20], "separators": []}, "not inside 14 digits"),
        ({"digits": 14, "api10_slice": [0, 10], "separators": "-"}, "list of characters"),
        ({"digits": 14, "api10_slice": [0, 10], "separators": ["--"]}, "single non-digit"),
        ({"digits": 14, "api10_slice": [0, 10], "separators": ["0"]}, "single non-digit"),
    ],
)
def test_a_malformed_identity_spec_fails_where_it_is_read_not_where_it_is_used(spec, message):
    with pytest.raises(RuleSpecError, match=message):
        api10_identity(mpr_rule().model_copy(update={"spec": spec}))
