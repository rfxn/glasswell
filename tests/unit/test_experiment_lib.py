"""F35: `gw_die` fires inside a command substitution, so the experiment kept going.

`gw_psql` calls `psql "$(gw_dsn)"`. When `db.env` is unreadable `gw_dsn` calls `gw_die`, whose
`exit 2` terminates only the `$()` subshell — `psql ""` then runs against whatever `PG*` in the
caller's environment points at, and the experiment emits a `VERDICT|` line computed from the
wrong database. Experiments are held to a lower bar than the pipeline, but silently producing
a wrong answer is not the lower bar; failing is.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[2] / "scripts" / "experiments" / "lib.sh"

pytestmark = pytest.mark.unit


@pytest.fixture
def experiment(tmp_path: Path):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    marker = tmp_path / "psql-ran"
    psql = binaries / "psql"
    psql.write_text(
        f'#!/bin/bash\nprintf \'%s\\n\' "$1" >> {marker}\ncat >/dev/null\nexit 0\n',
        encoding="utf-8",
    )
    psql.chmod(0o755)

    def run(body: str, **environment: str) -> tuple[subprocess.CompletedProcess, str]:
        script = tmp_path / "experiment.sh"
        # Every experiment opens with these flags and calls gw_psql with a heredoc, so the
        # harness has to as well: on the right of a pipe gw_psql is a subshell and nothing it
        # returns can stop the caller.
        script.write_text(
            f'#!/bin/bash\nset -euo pipefail\n. "{LIB}"\n{body}\n', encoding="utf-8"
        )
        completed = subprocess.run(
            ["/bin/bash", str(script)],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PATH": f"{binaries}:{os.environ['PATH']}",
                "GLASSWELL_DB_ENV": str(tmp_path / "absent.env"),
                **environment,
            },
            check=False,
        )
        return completed, marker.read_text(encoding="utf-8") if marker.exists() else ""

    return run


def test_an_unreadable_db_env_stops_the_experiment(experiment):
    completed, ran = experiment('gw_psql <<<"select 1"\nprintf "VERDICT|reached|1\\n"')

    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert "VERDICT|" not in completed.stdout
    assert ran == "", "psql ran with an empty DSN, against the caller's default database"


def test_the_refusal_names_the_file_it_could_not_read(experiment):
    completed, _ = experiment('gw_psql <<<"select 1"')

    assert "absent.env" in completed.stderr
    assert "GLASSWELL_SSH" in completed.stderr


def test_an_explicit_dsn_still_runs(experiment):
    """The floor: refusing everything would satisfy the assertions above."""
    completed, ran = experiment(
        'gw_psql <<<"select 1"\nprintf "VERDICT|reached|1\\n"',
        GLASSWELL_DSN="postgresql:///glasswell",
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "VERDICT|reached|1" in completed.stdout
    assert ran.strip() == "postgresql:///glasswell"


def test_a_readable_db_env_supplies_the_dsn(experiment, tmp_path):
    env_file = tmp_path / "db.env"
    env_file.write_text("DATABASE_URL=postgresql://reader@host/glasswell\n", encoding="utf-8")

    completed, ran = experiment('gw_psql <<<"select 1"', GLASSWELL_DB_ENV=str(env_file))

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert ran.strip() == "postgresql://reader@host/glasswell"


def test_gw_int_refuses_a_non_integer_from_the_top_level(experiment):
    completed, _ = experiment('gw_int "twelve"\nprintf "VERDICT|reached|1\\n"')

    assert completed.returncode == 2
    assert "VERDICT|" not in completed.stdout
