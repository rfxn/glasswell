"""UDM-SPEC §5.3: `/v1/wells/{api10}` keeps its name, its pattern and its meaning permanently.

Widening `API10_PATTERN` so the US path also accepts a Canadian UWI is formally a *relaxation* —
every previously valid request stays valid — so blueprint §3.6.1 does not forbid it and it looks
like the cheap way to serve a second jurisdiction. It is refused on two grounds, and this file
is the second one made mechanical (risk R-2).

Ground one, that the freeze gate could not see the change, is closed as a class by the `pattern`
fact kind in `openapi_diff.py`. Ground two is that `WellSummary.api10` and `WellDetail.api10` are
typed `str` and bound to the glossary term `gt_api_10_api_12_api_14`: a UWI arriving through a
widened path would be served under a name and a glossary binding that both say API-10, and the
differ cannot see that at all because the type is still `string`. A Canadian well is resolved
through the query resolver on `GET /v1/wells` (§5.2a), never through a widened path.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from glasswell.api.routers.wells import API10_PATTERN
from tests.contract.test_openapi_snapshot import SNAPSHOT_PATH

# AER Directive 059 Appendix 2's shape: 16 characters, and the thing §5.3 refuses to admit here.
UWI = "100062503507W400"


def _api10_parameters() -> dict[str, dict]:
    """Every `{api10}` path parameter the committed document declares, by operation."""
    document = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    found = {}
    for path, operations in document["paths"].items():
        if "{api10}" not in path:
            continue
        for method, operation in operations.items():
            for parameter in operation.get("parameters", ()):
                if parameter["name"] == "api10" and parameter["in"] == "path":
                    found[f"{method.upper()} {path}"] = parameter
    return found


def test_the_api10_grammar_is_ten_digits_and_the_ruling_is_that_it_stays_that_way() -> None:
    assert API10_PATTERN == r"^\d{10}$"


def test_every_served_api10_path_declares_that_grammar_rather_than_one_of_its_own() -> None:
    """A route that spelled its own pattern would move independently of the constant above."""
    declared = _api10_parameters()

    # The templated paths §5.1 freezes. A document that stopped serving them would pass
    # the loop below on an empty dictionary.
    assert sorted(declared) == [
        "GET /v1/wells/{api10}",
        "GET /v1/wells/{api10}/completions",
        "GET /v1/wells/{api10}/neighbors",
        "GET /v1/wells/{api10}/production",
        "GET /v1/wells/{api10}/production/pools",
        "GET /v1/wells/{api10}/type-curve",
    ]
    assert {route: parameter["schema"]["pattern"] for route, parameter in declared.items()} == {
        route: API10_PATTERN for route in declared
    }


def test_a_uwi_is_refused_by_the_united_states_path_rather_than_answered(
    client: TestClient,
) -> None:
    """The ruling's observable half: the pattern is enforced, not decorative."""
    response = client.get(f"/v1/wells/{UWI}")

    assert response.status_code == 422
