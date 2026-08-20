"""Identity: ULIDs, content addressing, handle and selector grammar (SB-07 §1.3, §2.1)."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any, NamedTuple

from glasswell.lineage.errors import InvalidHandle, InvalidSelector
from glasswell.lineage.models import InputRef, OutputSpec
from glasswell.lineage.serialization import canonical_json, hash_payload

DERIVATION_PREFIX = "drv_"
MANIFEST_PREFIX = "man_"
_ADDRESS_BYTES = 12

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_SELECTOR_KEY_RE = re.compile(r"\A[a-z][a-z0-9_]*\Z")
_SELECTOR_VALUE_RE = re.compile(r"\A[A-Za-z0-9_.:+-]+\Z")
_DERIVATION_ID_RE = re.compile(r"\Adrv_[a-z0-9]+\Z")


class Handle(NamedTuple):
    derivation_id: str
    selector: str | None


def new_ulid(now: datetime, entropy: bytes | None = None) -> str:
    """Time-ordered 26-char identifier; `now` is injected so callers stay clock-free."""
    if now.tzinfo is None:
        raise ValueError(f"datetime {now!r} must be timezone-aware")
    if entropy is None:
        entropy = secrets.token_bytes(10)
    if len(entropy) != 10:
        raise ValueError("ULID entropy must be 10 bytes")
    milliseconds = int(now.timestamp() * 1000)
    value = int.from_bytes(milliseconds.to_bytes(6, "big") + entropy, "big")
    return "".join(_CROCKFORD[(value >> shift) & 0x1F] for shift in range(125, -5, -5))


def manifest_id(sha256_hex_digest: str) -> str:
    if not _SHA256_RE.match(sha256_hex_digest):
        raise ValueError(f"not a lowercase hex sha256 digest: {sha256_hex_digest!r}")
    return MANIFEST_PREFIX + sha256_hex_digest[:32]


def ruleset_hash(rule_ids: Iterable[str]) -> str:
    """Order-independent: citation order is not a property of the ruleset."""
    return hash_payload(sorted(set(rule_ids)))


def derivation_id(
    *,
    operation: str,
    inputs: Sequence[InputRef],
    params: Mapping[str, Any],
    code_version: str,
    env_id: str,
    rule_ids: Iterable[str],
    output: OutputSpec,
) -> str:
    """Content address over the derivation *spec* — never over the artifact it produced."""
    address = {
        "operation": operation,
        "input_refs": [
            {
                "ord": ordinal,
                "kind": ref.kind,
                "ref_id": ref.ref_id,
                "selector": ref.selector,
                "as_of_vintage": ref.as_of_vintage,
                "role": ref.role,
            }
            for ordinal, ref in enumerate(inputs)
        ],
        "params_hash": hash_payload(params),
        "code_version": code_version,
        "env_id": env_id,
        "conformance_ruleset_hash": ruleset_hash(rule_ids),
        "output_dataset": output.dataset,
        "output_partition": dict(output.partition),
    }
    digest = hashlib.sha256(canonical_json(address)).digest()[:_ADDRESS_BYTES]
    return DERIVATION_PREFIX + base64.b32encode(digest).decode("ascii").rstrip("=").lower()


def parse_selector(selector: str) -> tuple[tuple[str, str], ...]:
    """Fixed key=value list. No operators, no expressions — the handle is attacker-reachable."""
    if not selector:
        raise InvalidSelector("selector is empty")
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for term in selector.split("&"):
        key, separator, value = term.partition("=")
        if not separator:
            raise InvalidSelector(f"selector term {term!r} is not key=value")
        if not _SELECTOR_KEY_RE.match(key):
            raise InvalidSelector(f"selector key {key!r} is not a declared key column")
        if not _SELECTOR_VALUE_RE.match(value):
            raise InvalidSelector(f"selector value {value!r} contains disallowed characters")
        if key in seen:
            raise InvalidSelector(f"selector key {key!r} appears twice")
        seen.add(key)
        pairs.append((key, value))
    return tuple(pairs)


def format_selector(pairs: Iterable[tuple[str, str]]) -> str:
    return "&".join(f"{key}={value}" for key, value in pairs)


def parse_handle(handle: str) -> Handle:
    derivation, separator, selector = handle.partition("#")
    if not _DERIVATION_ID_RE.match(derivation):
        raise InvalidHandle(f"{handle!r} does not start with a derivation id")
    if not separator:
        return Handle(derivation, None)
    parse_selector(selector)
    return Handle(derivation, selector)


def format_handle(derivation: str, selector: str | None = None) -> str:
    return f"{derivation}#{selector}" if selector else derivation
