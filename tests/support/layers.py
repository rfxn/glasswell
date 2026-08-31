"""Layer-boundary reads over a parsed module rather than over its text.

`assert "staging." not in source.read_text()` is a substring grep, and a substring grep is
defeated by writing the name in pieces: `"stag" + "ing" + "." + "nd_mpr_oil"` executes as a
staging read and greps clean. These helpers fold every statically-known string in the module
first -- concatenations and f-string parts included -- so what is searched is the value the
interpreter will build, not the spelling in the file.

What is still out of reach: a name assembled at runtime from data. Blueprint §3.0.1 is also
asserted against the relations actually touched, in the integration tier, wherever a fixture
can run the code; this is the static half.
"""

from __future__ import annotations

import ast
from pathlib import Path

# Stands in for an f-string placeholder whose value is not statically known, so a name split
# across a substitution (`f"{schema}.wells"`) cannot silently join into a false clean read.
UNKNOWN = "\x00"


def folded(node: ast.AST) -> str | None:
    """The string a node evaluates to, or None where that is not statically knowable."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = folded(node.left), folded(node.right)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                inner = folded(value.value)
                parts.append(UNKNOWN if inner is None else inner)
            else:
                inner = folded(value)
                if inner is None:
                    return None
                parts.append(inner)
        return "".join(parts)
    return None


def module_strings(source: str) -> list[str]:
    """Every statically-known string the module builds, sub-expressions included."""
    return [text for node in ast.walk(ast.parse(source)) if (text := folded(node)) is not None]


def schema_reads(source: str, schema: str) -> list[str]:
    """Every folded string naming `<schema>.`, deduplicated and ordered."""
    marker = f"{schema}."
    return sorted({text for text in module_strings(source) if marker in text})


def schema_reads_in(path: Path, schema: str) -> list[str]:
    return schema_reads(path.read_text(encoding="utf-8"), schema)
