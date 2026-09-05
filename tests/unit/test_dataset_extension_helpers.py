"""The two authoring helpers behind the document extensions, at the point of authorship.

`dataset()` and `semantics()` refuse a bad declaration when it is written rather than when the
document is linted, which is the difference between a typo caught at import and one caught in
CI. The lint itself, and every rule checked against the served document, is
tests/contract/test_dataset_extension.py -- these seven were cloning a seeded contract database
to call a pydantic model.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from glasswell.api.examples import DATASET_KEY, GLOSSARY_KEY, SEMANTICS_KEY, dataset, semantics


def _pivot() -> dict[str, Any]:
    """The rev-3 pivot shape, against the schema C2 will declare it on."""
    return {
        "id": "production",
        "title": "Production",
        "group": "wells",
        "collection_pointer": "",
        "series_pointer": "/series",
        "row_projection": {
            "axis": "/pm",
            "columns": ["/oil_bbl", "/gas_mcf", "/water_bbl"],
            "suffixes": ["_report_vintage", "_null_semantics", "_aggregation"],
        },
        "anchors": ["/api10", "/granularity", "/reporting_level"],
        "row_id": ["/pm"],
        "facets": ["stream", "from", "to"],
        "columns": {
            "default": ["/pm", "/oil_bbl", "/gas_mcf", "/water_bbl", "/granularity"],
            "hidden": [],
            "hidden_reason": {},
        },
        "intro": "nb_dataset_production",
        "order": 11,
    }


def test_the_helper_refuses_a_reserved_id_at_authoring_time() -> None:
    """The document lint is the gate; the model is the fast failure, so a typo never reaches it."""
    with pytest.raises(ValidationError, match="reserved"):
        dataset(**(_pivot() | {"id": "map"}))


def test_the_helper_refuses_a_member_a_1_does_not_define() -> None:
    """A misspelled member is how a declaration silently loses its columns (B5)."""
    with pytest.raises(ValidationError, match="Extra inputs"):
        dataset(**(_pivot() | {"column": {"default": ["/pm"]}}))


def test_the_helper_refuses_a_hidden_column_with_no_reason() -> None:
    fields = _pivot()
    fields["columns"]["hidden"] = ["/streams"]

    with pytest.raises(ValidationError, match="hidden_reason"):
        dataset(**fields)


def test_the_helper_omits_what_a_declaration_did_not_state() -> None:
    """`exclude_none` keeps the served document to what an author actually wrote — an absent
    `summary_operation` is absent, not `null`, and the fallback stays expressible."""
    fields = _pivot()
    fields["columns"].pop("default")

    payload = dataset(**fields)[DATASET_KEY]

    assert "summary_operation" not in payload
    assert "default" not in payload["columns"]
    assert payload["series_pointer"] == "/series"


def test_the_helper_refuses_an_entry_that_binds_nothing_and_says_nothing() -> None:
    with pytest.raises(ValidationError, match="is not written"):
        semantics(limit={})


def test_the_helper_refuses_a_term_id_that_is_not_one() -> None:
    """A term id that cannot exist fails here rather than at the R9 check's database round
    trip, which is the difference between a typo caught at import and one caught in CI."""
    with pytest.raises(ValidationError, match="pattern"):
        semantics(limit={"glossary": "report_vintage"})


def test_the_helper_serves_the_binding_under_the_key_r9_collects() -> None:
    """The call site may write `glossary=` for readability; the document may not (G-2)."""
    payload = semantics(as_of={"glossary": "gt_report_vintage", "so": "Selects the vintage."})

    assert payload[SEMANTICS_KEY]["as_of"] == {
        GLOSSARY_KEY: "gt_report_vintage",
        "so": "Selects the vintage.",
    }
