"""Both listeners strip credentials from their access log, and both need their own block.

A Caddy site does not inherit another site's `log`. The tunnel listener without one would
be logged by the default logger with no filter at all — which is the listener where a leaked
credential matters most, because it is the one the internet reaches.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from glasswell.api import REFUSED_QUERY_PARAMS
from glasswell.api.csrf import CSRF_HEADER
from glasswell.api.examples import KEY_HEADER

pytestmark = pytest.mark.unit

CADDYFILE = Path(__file__).resolve().parents[2] / "infra" / "caddy" / "Caddyfile"
DELETED_HEADERS = (KEY_HEADER, "Cookie", CSRF_HEADER)


def log_blocks() -> list[str]:
    text = CADDYFILE.read_text(encoding="utf-8")
    blocks = []
    for match in re.finditer(r"^\tlog \{$", text, re.MULTILINE):
        depth = 0
        for index in range(match.start(), len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(text[match.start() : index + 1])
                    break
    return blocks


def test_every_listener_that_proxies_has_its_own_log_block() -> None:
    """Two sites proxy to the API, so there are two log blocks. A missing one is silent."""
    assert len(log_blocks()) == 2, "a proxying listener has no log block of its own"


@pytest.mark.parametrize("header", DELETED_HEADERS)
def test_the_log_block_deletes_the_key_the_cookie_and_the_csrf_header(header: str) -> None:
    for block in log_blocks():
        assert f"request>headers>{header} delete" in block, f"{header} survives into a log"


@pytest.mark.parametrize("parameter", REFUSED_QUERY_PARAMS)
def test_the_log_block_deletes_every_refused_query_parameter(parameter: str) -> None:
    """The API refuses these outright, but an edge logs the URI before the origin sees it."""
    for block in log_blocks():
        assert re.search(rf"^\s*delete {parameter}$", block, re.MULTILINE), (
            f"?{parameter}= reaches the access log"
        )


def test_each_log_block_writes_somewhere_of_its_own() -> None:
    outputs = {
        re.search(r"output file (\S+)", block).group(1)
        for block in log_blocks()
        if re.search(r"output file (\S+)", block)
    }

    assert len(outputs) == len(log_blocks()), "two listeners share one log file"
