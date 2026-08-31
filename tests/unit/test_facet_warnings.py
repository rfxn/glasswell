"""`/v1/wells/facets` warnings: every `detail` a reader is served is a sentence, not a list."""

from __future__ import annotations

from glasswell.api.routers.facets import _warnings

UNREGISTERED_ABSENCE = {"label": "not reported", "rule_id": None}


def test_every_warning_detail_is_a_string_on_every_arm() -> None:
    """A stray comma inside the parens makes `detail` a 1-tuple. `meta.warnings` is typed
    `list[dict[str, Any]]`, so pydantic serialises it as a JSON array and nothing refuses it."""
    emitted = _warnings(
        state="42",
        dimension="operator",
        absence=UNREGISTERED_ABSENCE,
        truncated=True,
        q="chevron",
    )

    assert {warning["code"] for warning in emitted} == {
        "absence_unregistered",
        "list_truncated",
        "search_scopes_the_ranking",
    }
    for warning in emitted:
        assert isinstance(warning["detail"], str), f"{warning['code']}: {warning['detail']!r}"
        assert isinstance(warning["code"], str)
        assert isinstance(warning["pointer"], str)
