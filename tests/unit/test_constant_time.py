"""No secret is compared with `==` anywhere on the authentication path.

Grep-shaped by design: a timing measurement of a comparison is unreproducible on shared CI,
and a test that asserts "this took the same time" is the kind that gets disabled. Asserting
the *code* never uses the wrong primitive is the assertion that does not rot.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from glasswell.api import accounts, csrf, principal

pytestmark = pytest.mark.unit

MODULES = (accounts, csrf, principal)

# Names whose value is, or derives from, a credential. A comparison of one of these with ==
# leaks its content through timing, one byte at a time.
SECRET_NAMES = frozenset(
    {
        "token",
        "secret",
        "password",
        "presented",
        "sha256",
        "digest",
        "signature",
        "stored",
        "expected",
        "password_hash",
        "owner_key",
    }
)


def equality_comparisons(source: str) -> list[str]:
    """Every `a == b` / `a != b` in the module, rendered back to source."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Compare) and any(
            isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops
        ):
            found.append(ast.unparse(node))
    return found


def mentions_a_secret(expression: str) -> bool:
    tokens = set(ast.unparse(ast.parse(expression)).replace("(", " ").replace(")", " ").split())
    lowered = {token.strip(".,").lower() for token in tokens}
    return bool(lowered & SECRET_NAMES)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_secret_is_compared_with_double_equals(module) -> None:
    source = inspect.getsource(module)

    offenders = [
        comparison
        for comparison in equality_comparisons(source)
        if mentions_a_secret(comparison)
    ]

    assert offenders == [], (
        f"{module.__name__} compares a credential-derived value with ==; use"
        f" hmac.compare_digest: {offenders}"
    )


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_each_module_reaches_for_the_constant_time_primitive(module) -> None:
    """The floor under the test above: it would pass on a module that compares nothing."""
    source = inspect.getsource(module)

    assert "compare_digest" in source or "verify" in source


def test_the_static_owner_key_is_still_compared_in_constant_time() -> None:
    source = inspect.getsource(principal.resolve_principal)

    assert "hmac.compare_digest" in source


def test_the_session_lookup_compares_the_fetched_hash_in_constant_time() -> None:
    source = inspect.getsource(accounts.resolve_session)

    assert "compare_digest" in source


def test_no_module_on_the_auth_path_imports_a_naive_comparison_helper() -> None:
    """A sweep, so a new module on this path is covered without editing MODULES."""
    root = Path(principal.__file__).resolve().parent
    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        offenders = [
            comparison
            for comparison in equality_comparisons(source)
            if mentions_a_secret(comparison)
        ]
        assert offenders == [], f"{path.name}: {offenders}"
