"""F11: what `deploy.sh` restarts, and what it waits for before asserting on it.

Step 7 restarts `glasswell-api` and `martin`. Step 7b polls the API's `/healthz` for up to 30s
— added after the v0.20 deploy, where verify.sh probed a socket uvicorn had not re-bound and
read six 000s. martin got the restart and not the wait, so verify.sh's per-layer catalogue
assertions ran against a process that reads its whole source catalogue from PostgreSQL at
startup. That fails a deploy that was fine, which is how an operator learns to re-run the gate
rather than read it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[2] / "scripts" / "deploy.sh"

pytestmark = pytest.mark.unit


def script() -> str:
    return DEPLOY.read_text(encoding="utf-8")


def steps() -> dict[str, str]:
    """The script's own numbered steps, each mapped to the code that follows it. Comments are
    dropped: a comment introducing the *next* step sits inside this one's span, and prose
    naming an endpoint is not the same as polling it."""
    marks = list(re.finditer(r'^step "(\d+[a-z]?)\. ([^"]+)"', script(), re.MULTILINE))
    assert marks, "deploy.sh declares no steps"
    bodies = {}
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(script())
        body = script()[mark.start() : end]
        bodies[mark.group(1)] = "\n".join(
            line for line in body.splitlines() if not line.lstrip().startswith("#")
        )
    return bodies


def step_holding(needle: str) -> str:
    matched = [number for number, body in steps().items() if needle in body]
    assert len(matched) == 1, f"{needle!r} appears in steps {matched}"
    return matched[0]


def order(number: str) -> tuple[int, str]:
    """Sort key over `7`, `7b`, `8` — the script's own numbering, not source offsets."""
    digits = re.match(r"(\d+)([a-z]?)", number)
    assert digits is not None
    return int(digits.group(1)), digits.group(2)


def test_the_deploy_restarts_the_services_this_file_reasons_about() -> None:
    """A floor: every ordering assertion below is vacuous if nothing is restarted."""
    assert set(re.findall(r"systemctl restart ([a-z-]+)", script())) == {"glasswell-api", "martin"}


@pytest.mark.parametrize(
    ("service", "probe"), [("glasswell-api", "/healthz"), ("martin", "/catalog")]
)
def test_every_restarted_service_is_waited_on_before_verify_runs(service: str, probe: str) -> None:
    restart = order(step_holding(f"systemctl restart {service}"))
    verify = order(step_holding("infra/verify.sh"))
    waits = {
        number: body
        for number, body in steps().items()
        if probe in body and "systemctl restart" not in body
    }

    assert len(waits) == 1, f"no single step waits on {probe}: {sorted(waits)}"
    readiness = order(next(iter(waits)))
    assert restart <= readiness < verify
    assert "refuse" in next(iter(waits.values())), f"the {service} wait cannot fail the deploy"


def test_the_step_numbering_the_ordering_reads_is_unique() -> None:
    """`steps()` keys on the label, so a duplicated `7c` would silently drop a step and make
    the ordering above answer about the wrong body."""
    labels = re.findall(r'^step "(\d+[a-z]?)\. ', script(), re.MULTILINE)
    assert len(labels) == len(set(labels)), labels
    assert labels == sorted(labels, key=order), labels


def test_the_readiness_loops_do_not_word_split_a_command_substitution() -> None:
    """`for _ in $(seq 1 30)` is the shell-standards `for x in $(…)` shape; the bound is a
    literal here, so an arithmetic loop says the same thing without the substitution."""
    assert re.search(r"for\s+\w+\s+in\s+\$\(", script()) is None
