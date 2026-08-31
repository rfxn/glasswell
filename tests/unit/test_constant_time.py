"""No secret is compared with `==` anywhere on the authentication path.

Grep-shaped by design: a timing measurement of a comparison is unreproducible on shared CI,
and a test that asserts "this took the same time" is the kind that gets disabled. Asserting
the *code* never uses the wrong primitive is the assertion that does not rot.

Read from the parsed module, not from its text. `"hmac.compare_digest" in source` is satisfied
by a comment, and a name allowlist applied to the comparison as written is defeated by
`_a, _b = presented, owner_key` -- two renamed locals and the guard sees nothing. So the
primitive is asserted as a `Call` node, and every operand of an `==` is followed back through
the assignments that bound it before it is judged.
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
# leaks its content through timing, one byte at a time. The allowlist ages badly on its own,
# which is why `secret_operands` resolves aliases into it rather than matching the text.
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

# What counts as reaching for the constant-time primitive: argon2's `verify` is constant-time
# by construction, and `hmac.compare_digest` is the answer everywhere else.
CONSTANT_TIME = frozenset({"compare_digest", "verify", "verify_password", "verify_user_password"})


def calls(source: str) -> set[str]:
    """Every callee actually invoked, rendered as written -- `hmac.compare_digest`, `verify`."""
    return {
        ast.unparse(node.func)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
    }


def identifiers(node: ast.AST) -> set[str]:
    """Every name an expression reads: locals, attributes and string subscripts alike, so
    `user.password_hash` and `row["sha256"]` are as visible as a bare local.

    `len(...)` is stepped over. A fixed-size token's length is public, so comparing it is not
    a comparison of the secret's content.
    """
    found: set[str] = set()
    pending = [node]
    while pending:
        current = pending.pop()
        if (
            isinstance(current, ast.Call)
            and isinstance(current.func, ast.Name)
            and current.func.id == "len"
        ):
            continue
        if isinstance(current, ast.Name):
            found.add(current.id.lower())
        elif isinstance(current, ast.Attribute):
            found.add(current.attr.lower())
        elif isinstance(current, ast.Constant) and isinstance(current.value, str):
            found.add(current.value.lower())
        pending.extend(ast.iter_child_nodes(current))
    return found


def bound_names(target: ast.AST) -> set[str]:
    return {
        child.id.lower() if isinstance(child, ast.Name) else child.attr.lower()
        for child in ast.walk(target)
        if isinstance(child, (ast.Name, ast.Attribute))
    }


def _pairs(target: ast.AST, value: ast.AST) -> list[tuple[ast.AST, ast.AST]]:
    """Unpack `a, b = x, y` element-wise; anything else binds the whole right-hand side."""
    if (
        isinstance(target, (ast.Tuple, ast.List))
        and isinstance(value, (ast.Tuple, ast.List))
        and len(target.elts) == len(value.elts)
    ):
        return [pair for t, v in zip(target.elts, value.elts, strict=True) for pair in _pairs(t, v)]
    return [(target, value)]


# A rename moves a value; a call transforms it. `principal = resolve_principal(presented=...)`
# is not the credential, so following calls would report every object downstream of one.
_RENAME_NODES = (ast.Name, ast.Attribute, ast.Subscript, ast.Tuple, ast.List, ast.Starred,
                 ast.Constant, ast.expr_context)


def is_rename(value: ast.AST) -> bool:
    return all(isinstance(node, _RENAME_NODES) for node in ast.walk(value))


def origins(tree: ast.AST) -> dict[str, set[str]]:
    """Every name a rename bound, mapped to the names the value came from."""
    found: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            pairs = [pair for target in node.targets for pair in _pairs(target, node.value)]
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            pairs = _pairs(node.target, node.value) if node.value is not None else []
        else:
            continue
        for target, value in pairs:
            if not is_rename(value):
                continue
            for name in bound_names(target):
                found.setdefault(name, set()).update(identifiers(value))
    return found


def resolve(names: set[str], sources: dict[str, set[str]]) -> set[str]:
    """`names` plus everything they were assigned from, transitively."""
    seen: set[str] = set()
    pending = list(names)
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        pending.extend(sources.get(name, ()))
    return seen


def secret_comparisons(source: str) -> list[str]:
    """Every `a == b` / `a != b` whose operands resolve to a credential-derived name."""
    tree = ast.parse(source)
    sources = origins(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or not any(
            isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops
        ):
            continue
        operands: set[str] = set()
        for part in (node.left, *node.comparators):
            operands |= identifiers(part)
        if resolve(operands, sources) & SECRET_NAMES:
            found.append(ast.unparse(node))
    return found


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_secret_is_compared_with_double_equals(module) -> None:
    source = inspect.getsource(module)

    offenders = secret_comparisons(source)

    assert offenders == [], (
        f"{module.__name__} compares a credential-derived value with ==; use"
        f" hmac.compare_digest: {offenders}"
    )


def test_the_alias_a_renamed_local_hides_behind_is_still_seen() -> None:
    """The floor under the test above, and the mutation that used to walk past it: two locals
    carry the operands, the comparison names neither secret, and the leak is unchanged."""
    renamed = (
        "def f(presented, owner_key):\n"
        "    _a, _b = presented, owner_key\n"
        "    return _a == _b\n"
    )

    assert secret_comparisons(renamed) == ["_a == _b"]
    assert secret_comparisons("def f(a, b):\n    return a == b\n") == []


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_each_module_reaches_for_the_constant_time_primitive(module) -> None:
    """The floor under the test above: it would pass on a module that compares nothing.

    A call, not a mention: a comment naming `hmac.compare_digest` is what let the owner key be
    compared with `==` under a green suite.
    """
    invoked = {name.rsplit(".", 1)[-1] for name in calls(inspect.getsource(module))}

    assert invoked & CONSTANT_TIME, f"{module.__name__} never calls a constant-time comparison"


def test_the_static_owner_key_is_still_compared_in_constant_time() -> None:
    assert "hmac.compare_digest" in calls(inspect.getsource(principal.resolve_principal))


def test_the_session_lookup_compares_the_fetched_hash_in_constant_time() -> None:
    assert "hmac.compare_digest" in calls(inspect.getsource(accounts.resolve_session))


def test_no_module_on_the_auth_path_imports_a_naive_comparison_helper() -> None:
    """A sweep, so a new module on this path is covered without editing MODULES."""
    root = Path(principal.__file__).resolve().parent
    checked = 0
    for path in sorted(root.rglob("*.py")):
        checked += 1
        offenders = secret_comparisons(path.read_text(encoding="utf-8"))
        assert offenders == [], f"{path.name}: {offenders}"

    assert checked > 1, "the sweep found no modules, so it cannot fail"
