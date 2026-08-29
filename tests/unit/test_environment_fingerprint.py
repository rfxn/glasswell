"""F36: `app.env.example` pins the lockfile fingerprint and nothing checked the pin.

`derive()` stamps `GLASSWELL_LOCKFILE_SHA256` on every lineage node as the environment a
number was computed under. `install.sh` copies the example to `/etc/glasswell/app.env` on a
fresh host, so a dependency bump that regenerates the lockfile without updating the example
gives every node derived before the first `deploy.sh` step 5c a fingerprint that is a lie.
The window is narrow — deploy stamps `code-version.env`, loaded last — but a provenance value
under no-naked-numbers is not a thing to leave unchecked.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP_ENV_EXAMPLE = ROOT / "infra" / "env" / "app.env.example"
LOCKFILE = ROOT / "requirements.lock"
PIN = "GLASSWELL_LOCKFILE_SHA256"

pytestmark = pytest.mark.unit


def pinned() -> str:
    found = re.search(rf"^{PIN}=([0-9a-f]{{64}})$", APP_ENV_EXAMPLE.read_text(), re.MULTILINE)
    assert found is not None, f"{APP_ENV_EXAMPLE.name} carries no 64-hex {PIN}"
    return found.group(1)


def test_the_pinned_fingerprint_is_the_lockfiles_digest() -> None:
    assert pinned() == hashlib.sha256(LOCKFILE.read_bytes()).hexdigest(), (
        f"{PIN} in {APP_ENV_EXAMPLE.name} does not match requirements.lock — regenerate it with"
        f" `sha256sum requirements.lock` in the same commit as the dependency change"
    )


def test_the_lockfile_is_not_empty() -> None:
    """A floor: the digest of an empty file would satisfy the assertion above just as well."""
    assert LOCKFILE.stat().st_size > 0
    assert len(LOCKFILE.read_text().splitlines()) > 10
