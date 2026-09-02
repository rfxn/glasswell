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


@pytest.mark.parametrize(
    "population",
    ["glasswell.marts.cumulatives", "glasswell-fracfocus --promote-design"],
)
def test_every_population_step_runs_before_the_gate_that_asserts_on_it(population: str) -> None:
    """verify.sh counts rows in the tables these steps write. An ordering that is right today
    and unasserted is right until someone reorders it."""
    populate = order(step_holding(population))
    verify = order(step_holding("infra/verify.sh"))

    assert populate < verify


@pytest.mark.parametrize(
    "population",
    ["glasswell.marts.cumulatives", "glasswell-fracfocus --promote-design"],
)
def test_no_population_step_can_be_skipped_or_fail_silently(population: str) -> None:
    """The refusal is the safety layer: a deploy that half-populated a mart must not ship."""
    body = steps()[step_holding(population)]

    assert "|| refuse" in body
    assert not re.search(r"^\s*(if|case|while)\b", body, re.MULTILINE), body


def test_the_caddy_config_step_installs_reloads_and_refuses_on_an_inactive_caddy() -> None:
    """install.sh places the Caddyfile only under --with-caddy, which a routine deploy never
    passes, so a log-filter change shipped in the tree sat unapplied until someone noticed."""
    caddy = steps()[step_holding("/etc/caddy/Caddyfile")]

    assert "cmp -s" in caddy, "an unconditional install would reload caddy on every deploy"
    assert "systemctl reload caddy" in caddy
    assert "systemctl is-active --quiet caddy" in caddy
    assert caddy.count("refuse") >= 3, "each failure has to be able to fail the deploy"


def test_the_caddy_step_never_validates_outside_the_units_environment() -> None:
    """`caddy validate` run from the deploy has no CF_API_TOKEN, so the tls block it reads
    refuses a config that is correct. The reload validates with the unit's own environment."""
    assert "caddy validate" not in script()


def test_the_caddy_step_runs_after_the_config_install_and_before_the_restart() -> None:
    caddy = order(step_holding("/etc/caddy/Caddyfile"))
    units = order(step_holding("infra && ./install.sh"))
    restart = order(step_holding("systemctl restart glasswell-api"))

    assert units < caddy < restart


def test_the_scheduler_step_starts_the_timer_and_never_the_service() -> None:
    """A tick reads the whole registry and every source's poll evidence; a deploy step must
    not wait on it, and while every row observes there is nothing to launch either way."""
    body = steps()[step_holding("glasswell-scheduler.timer")]

    assert "systemctl start glasswell-scheduler.timer" in body
    assert "systemctl start glasswell-scheduler.service" not in script()
