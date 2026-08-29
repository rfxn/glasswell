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

from glasswell.ingest.base import LOCKFILE_SHA256_ENV
from glasswell.modeling import p3_publication

ROOT = Path(__file__).resolve().parents[2]
APP_ENV_EXAMPLE = ROOT / "infra" / "env" / "app.env.example"
INSTALL = ROOT / "infra" / "install.sh"
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


def test_the_pin_is_the_name_and_the_file_the_publication_gate_reads() -> None:
    """The assertion above is only load-bearing while it names what the code names. A rename
    of the variable, or a move of the lockfile, would leave it green and inert."""
    assert LOCKFILE_SHA256_ENV == PIN
    assert p3_publication.REQUIREMENTS_LOCK == LOCKFILE


def test_a_stale_pin_refuses_the_p3_publication_rather_than_mis_stamping_it() -> None:
    """Why the drift is fatal and not cosmetic: `_environment` compares the declared pin to the
    lockfile's own digest and fails closed, so an example that has drifted cannot publish P3 at
    all on a fresh host."""
    source = Path(p3_publication.__file__).read_text(encoding="utf-8")

    refusal = (
        r"if actual_lock_sha256 != declared_lock_sha256:\s*\n"
        r"\s*_fail\(\"lockfile_stamp_mismatch\"\)"
    )

    assert re.search(refusal, source), (
        "the publication gate no longer refuses a declared fingerprint that disagrees"
    )


def test_a_fresh_host_inherits_the_pin_from_the_example_verbatim() -> None:
    """`install.sh` seeds /etc/glasswell/app.env from the example and rewrites only the owner
    key, which is what carries a stale pin onto every fresh host."""
    seeding = INSTALL.read_text(encoding="utf-8")

    assert "env/app.env.example" in seeding
    assert re.search(r'sed "s\|\^GLASSWELL_OWNER_KEY=', seeding), (
        "install.sh no longer seeds app.env by rewriting only the owner key"
    )
    assert PIN not in seeding, f"install.sh rewrites {PIN}, so the example's pin is not the stamp"
