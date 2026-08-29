"""`emitted_by_this_slice` is served, so it has to be true.

`GET /v1` and `GET /v1/errors/{code}` publish the flag as "whether this slice can emit the
code". A code this slice raises while declaring `emitted=False` is a served falsehood about the
service's own behaviour, which is the one thing the error registry exists to describe.
"""

from __future__ import annotations

import ast
from pathlib import Path

from glasswell.api.errors import ERROR_REGISTRY

SOURCE = Path(__file__).parents[2] / "src" / "glasswell"


def raised_codes() -> set[str]:
    """Every literal code passed as the first argument to `ProblemError(...)` in the tree."""
    codes: set[str] = set()
    for path in sorted(SOURCE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            name = getattr(function, "id", None) or getattr(function, "attr", None)
            if name != "ProblemError" or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                codes.add(first.value)
    return codes


def test_every_code_this_slice_raises_declares_itself_emitted() -> None:
    raised = raised_codes()

    # A floor: an AST walk that matched nothing would otherwise pass by finding no raises.
    assert len(raised) >= 10, f"only {len(raised)} raise sites found; the walk is not working"

    undeclared = sorted(
        code for code in raised if code in ERROR_REGISTRY and not ERROR_REGISTRY[code].emitted
    )

    assert undeclared == [], (
        f"{undeclared} are raised in src/ but served as emitted_by_this_slice=false"
    )


def test_every_raised_code_is_in_the_registry() -> None:
    """A raised code with no spec would serve a problem document the registry cannot explain."""
    assert sorted(code for code in raised_codes() if code not in ERROR_REGISTRY) == []
