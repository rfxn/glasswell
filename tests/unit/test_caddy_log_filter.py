"""Both listeners strip credentials from their access log, and both need their own block.

A Caddy site does not inherit another site's `log`. The tunnel listener without one would
be logged by the default logger with no filter at all — which is the listener where a leaked
credential matters most, because it is the one the internet reaches.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from glasswell.api import REFUSED_QUERY_PARAMS, UNREAD_CREDENTIAL_HEADERS
from glasswell.api.access_log import redact
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


@pytest.mark.parametrize("header", UNREAD_CREDENTIAL_HEADERS)
def test_the_log_block_deletes_the_headers_a_caller_guesses_the_key_into(header: str) -> None:
    """The API reads none of these, so a request carrying one is refused -- and logged first,
    header value intact. That is the whole incident: a probe sent the owner key in X-Api-Key,
    got its 403, and left the key in tunnel.log. Redaction cannot depend on the API agreeing
    that a header is a credential."""
    for block in log_blocks():
        assert f"request>headers>{header} delete" in block, f"{header} survives into a log"


@pytest.mark.parametrize("header", UNREAD_CREDENTIAL_HEADERS)
def test_no_route_reads_a_header_the_log_filter_redacts(header: str) -> None:
    """Redacting a header the API does read would hide a live credential path from the log
    rather than keep a dead one out of it."""
    read_by = [
        f"{path}:{number}"
        for path in (Path(__file__).resolve().parents[2] / "src" / "glasswell").rglob("*.py")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if f'"{header}"' in line and "UNREAD_CREDENTIAL_HEADERS" not in line
    ]

    assert not read_by, f"{header} is named in {read_by}; it is not an unread header"


@pytest.mark.parametrize("parameter", REFUSED_QUERY_PARAMS)
def test_the_log_block_deletes_every_refused_query_parameter(parameter: str) -> None:
    """The API refuses these outright, but an edge logs the URI before the origin sees it."""
    for logged in redacted_at_the_edge(parameter):
        assert "OWNERKEY" not in logged, f"?{parameter}= reaches the access log"


def test_each_log_block_writes_somewhere_of_its_own() -> None:
    outputs = {
        re.search(r"output file (\S+)", block).group(1)
        for block in log_blocks()
        if re.search(r"output file (\S+)", block)
    }

    assert len(outputs) == len(log_blocks()), "two listeners share one log file"


# Names the API refuses outright, plus the shapes a caller reaches for when it will not take
# them. Over-redacting is the safe direction and the API's own filter already says so: a
# redacted log value is recoverable from the request, a leaked credential is not.
# The four the API refuses have their own case above; these are the shapes it does not name.
CREDENTIAL_QUERY_NAMES = (
    "api_key",
    "apikey",
    "owner_key",
    "access_token",
    "refresh_token",
    "id_token",
    "secret",
    "client_secret",
    "session",
    "session_id",
    "csrf",
    "csrf_token",
    "auth",
    "authorization",
    "passwd",
)
# Served parameters. A log that redacts these stops being readable, which is its own failure.
SERVED_QUERY_NAMES = ("limit", "cursor", "as_of", "valid_at", "source_id", "bbox", "include")


def uri_regexps() -> list[re.Pattern[str]]:
    """The `request>uri regexp` of each log block, compiled as Caddy compiles it.

    Go's RE2 and `re` agree on this subset -- character classes, a non-capturing alternation
    and one group -- so the pattern the file ships is the pattern under test, not a copy.
    """
    compiled = []
    for block in log_blocks():
        match = re.search(r'request>uri regexp "(.+?)" "(.+?)"$', block, re.MULTILINE)
        assert match, "a log block does not redact its URI by pattern"
        compiled.append((re.compile(match.group(1)), match.group(2)))
    return compiled


def redacted_at_the_edge(name: str) -> list[str]:
    """What each listener would log for `GET /v1/wells?<name>=OWNERKEY HTTP/1.1`."""
    line = f"/v1/wells?{name}=OWNERKEY&limit=5"
    return [
        pattern.sub(re.sub(r"\$\{(\d+)\}", r"\\g<\1>", replacement), line)
        for pattern, replacement in uri_regexps()
    ]


def fields_entries() -> list[list[str]]:
    """The field names each `fields` block declares, one list per block."""
    declared = []
    for block in log_blocks():
        start = block.index("fields {") + len("fields {")
        depth, names = 1, []
        for line in block[start:].splitlines():
            stripped = line.strip()
            if depth == 1 and stripped and not stripped.startswith("#") and stripped != "}":
                names.append(stripped.split()[0])
            depth += stripped.count("{") - stripped.count("}")
            if depth == 0:
                break
        declared.append(names)
    return declared


@pytest.mark.parametrize("name", CREDENTIAL_QUERY_NAMES)
def test_the_uri_pattern_covers_every_credential_shaped_query_parameter(name: str) -> None:
    """`delete key` covered the four names the API refuses and nothing else. A caller who
    guesses `?api_key=` gets a 422 and leaves the key in the log, which is REG-V3's incident
    one field along."""
    for logged in redacted_at_the_edge(name):
        assert "OWNERKEY" not in logged, f"?{name}= reaches the access log in full"
        assert "limit=5" in logged, f"?{name}= redaction ate the rest of the query"


@pytest.mark.parametrize("name", SERVED_QUERY_NAMES)
def test_the_uri_pattern_leaves_the_served_parameters_readable(name: str) -> None:
    for logged in redacted_at_the_edge(name):
        assert f"{name}=OWNERKEY" in logged, f"?{name}= is redacted; the log stops being usable"


@pytest.mark.parametrize("name", CREDENTIAL_QUERY_NAMES + SERVED_QUERY_NAMES)
def test_the_edge_redacts_everything_the_origin_redacts(name: str) -> None:
    """The API's own filter is the second line for anything that reaches uvicorn. The edge
    logs first, so it must not be the looser of the two."""
    line = f"/v1/wells?{name}=OWNERKEY&limit=5"
    if redact(line) == line:
        return
    for logged in redacted_at_the_edge(name):
        assert "OWNERKEY" not in logged, f"the origin redacts ?{name}= and the edge does not"


def test_no_log_block_declares_one_field_twice() -> None:
    """Caddy's `fields` is a map: a second entry for a field replaces the first silently, so
    two filters on `request>uri` ship as whichever the adapter read last."""
    for names in fields_entries():
        duplicates = sorted({name for name in names if names.count(name) > 1})
        assert not duplicates, f"a later filter silently replaces an earlier one: {duplicates}"


def test_both_listeners_redact_their_uri_the_same_way() -> None:
    assert len({(pattern.pattern, value) for pattern, value in uri_regexps()}) == 1
