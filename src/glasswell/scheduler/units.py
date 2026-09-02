"""What a launched job's transient unit looks like, and what an installed timer already drives.

The hardening block is carried as one tuple rather than rendered per job: the unit this
scheduler replaces confines its jobs with exactly these fourteen directives, and a job the
scheduler launches has to be confined the same way or retirement quietly loses the sandbox.
`test_scheduler_units.py` parses `glasswell-ingest.service` and holds this tuple to it, so the
assertion tracks the shipped unit rather than a copy of it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

VENV_PYTHON = "/opt/glasswell/venv/bin/python"
# No password reaches the process table: the same socket DSN the pipeline units carry today.
SOCKET_DSN = "postgresql:///glasswell?host=/var/run/postgresql"
APP_ENV = "/etc/glasswell/app.env"
CODE_VERSION_ENV = "-/etc/glasswell/code-version.env"

# glasswell-ingest.service:40-53, verbatim. ReadWritePaths is the union rather than a per-job
# narrowing because that is precisely today's posture under the single unit, so retirement
# changes nothing; a per-job column can narrow it later without a schema break.
TRANSIENT_HARDENING: tuple[str, ...] = (
    "NoNewPrivileges=yes",
    "ProtectSystem=strict",
    "ProtectHome=yes",
    "PrivateTmp=yes",
    "PrivateDevices=yes",
    "ProtectKernelTunables=yes",
    "ProtectKernelModules=yes",
    "ProtectControlGroups=yes",
    "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
    "RestrictSUIDSGID=yes",
    "LockPersonality=yes",
    "CapabilityBoundingSet=",
    "StateDirectory=glasswell",
    "ReadWritePaths=/var/lib/glasswell /data/raw /data/staging",
)

_DIRECTIVE_KEYS = frozenset(directive.split("=", 1)[0] for directive in TRANSIENT_HARDENING)


def hardening_directives(unit_text: str) -> tuple[str, ...]:
    """The `[Service]` hardening lines of a shipped unit, in file order."""
    body = unit_text.split("[Service]", 1)[-1].split("[Install]", 1)[0]
    return tuple(
        line.strip()
        for line in body.splitlines()
        if line.strip() and line.split("=", 1)[0].strip() in _DIRECTIVE_KEYS
    )


def transient_unit_name(job_id: str, run_id: str) -> str:
    """One unit per run, named so `systemctl show` can find it from the ledger row alone."""
    return f"gw-job-{job_id}-{run_id.rsplit('_', 1)[-1][-8:].lower()}"


def render_transient_argv(
    *,
    job_id: str,
    run_id: str,
    entry_point: str,
    argv: Sequence[str],
    run_as: str,
    memory_max: str | None,
    timeout_seconds: int | None,
) -> tuple[str, ...]:
    """The `systemd-run` command line for one job. Never carries a DSN on the command line."""
    rendered: list[str] = [
        "systemd-run",
        f"--unit={transient_unit_name(job_id, run_id)}",
        "--wait",
        "--quiet",
        f"--property=User={run_as}",
        f"--property=Group={run_as}",
    ]
    if timeout_seconds is not None:
        rendered.append(f"--property=TimeoutStartSec={timeout_seconds}")
    if memory_max is not None:
        rendered.append(f"--property=MemoryMax={memory_max}")
    rendered.append(f"--property=Environment=GLASSWELL_DSN={SOCKET_DSN}")
    rendered.append(f"--property=EnvironmentFile={APP_ENV}")
    rendered.append(f"--property=EnvironmentFile={CODE_VERSION_ENV}")
    rendered.extend(f"--property={directive}" for directive in TRANSIENT_HARDENING)
    rendered.extend([VENV_PYTHON, "-m", entry_point, *argv])
    return tuple(rendered)


_MODULE = re.compile(r"-m\s+(glasswell\.[a-z0-9_.]+)")


def timer_owned_entry_points(
    unit_texts: Sequence[str], console_scripts: Mapping[str, str]
) -> frozenset[str]:
    """The module paths installed units already drive, for the permanent double-run guard.

    Each `ExecStart=` is scanned as a whole directive value, never tokenised: one shipped line
    wraps its command in `/bin/bash -c '...'`, so the module sits inside a quoted argument and
    a positional read returns `-c`. A line that names a console script instead of a module is
    resolved through `[project.scripts]` by its full `<venv>/bin/<name>` path -- never by
    basename, which would let one script name match another entry's suffix.
    """
    owned: set[str] = set()
    for text in unit_texts:
        for value in re.findall(r"^ExecStart=(.*)$", text, re.MULTILINE):
            module = _MODULE.search(value)
            if module is not None:
                owned.add(module.group(1))
                continue
            for name, target in console_scripts.items():
                if re.search(rf"(?:^|[\s'\"])/\S*/bin/{re.escape(name)}(?:\s|$|['\"])", value):
                    owned.add(target.split(":", 1)[0])
    return frozenset(owned)
