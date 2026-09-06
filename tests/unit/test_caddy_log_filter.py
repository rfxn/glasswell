"""Both listeners strip credentials from their access log, and both need their own block.

A Caddy site does not inherit another site's `log`. The tunnel listener without one would
be logged by the default logger with no filter at all — which is the listener where a leaked
credential matters most, because it is the one the internet reaches.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from glasswell.api import REFUSED_QUERY_PARAMS, UNREAD_CREDENTIAL_HEADERS
from glasswell.api.access_log import CREDENTIAL_QUERY_STEMS, redact
from glasswell.api.csrf import CSRF_HEADER
from glasswell.api.examples import KEY_HEADER

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = ROOT / "infra" / "caddy" / "Caddyfile"
OPENAPI = ROOT / "tests" / "contract" / "openapi_snapshot.json"
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


# Names that reached a log in full at some point: `api_key` took its 422 through the four-name
# delete list (REG-V3), and the v0.83 sentinel's live caddy probe logged the other eight through
# the first alternation. A regression corpus, not the definition of the class -- that is
# CREDENTIAL_QUERY_STEMS, and the cases below are generated from it.
LOGGED_IN_FULL_ONCE = (
    "api_key",
    "pwd",
    "pass",
    "credential",
    "sig",
    "signature",
    "jwt",
    "bearer",
    "otp",
)
# The served names the class eats, by design: a stem inside an identifier is redacted, and
# `source_key` carries one. The origin redacts it the same way. A new served name that lands
# here is a naming decision to take, not a silent loss of the log.
OVER_REDACTED_SERVED = frozenset({"source_key"})


def generated_names() -> list[str]:
    """One name per shape a caller reaches for, per stem: bare, prefixed, suffixed, hyphenated
    and capitalised. Derived, so a stem added to the origin is probed here without an edit."""
    return [
        shape
        for stem in CREDENTIAL_QUERY_STEMS
        for shape in (stem, f"x_{stem}", f"{stem}_id", f"X-{stem.capitalize()}-2")
    ]


def served_query_names() -> list[str]:
    """Every query parameter the committed OpenAPI document serves."""
    document = json.loads(OPENAPI.read_text(encoding="utf-8"))
    return sorted(
        {
            parameter["name"]
            for item in document["paths"].values()
            for operation in item.values()
            if isinstance(operation, dict)
            for parameter in operation.get("parameters", [])
            if parameter.get("in") == "query"
        }
    )


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


def shipped_alternations() -> list[list[str]]:
    """The stem alternation each log block ships, read out of the file."""
    alternations = []
    for pattern, _ in uri_regexps():
        match = re.search(r"\(\?:([^()]+)\)", pattern.pattern)
        assert match, f"no stem alternation in {pattern.pattern!r}"
        alternations.append(match.group(1).split("|"))
    return alternations


def test_the_shipped_alternation_is_the_origin_stem_list_verbatim() -> None:
    """One list, two filters. The edge logs first, and a stem the origin learns that the edge
    does not is the sentinel's eight leaks again."""
    for alternation in shipped_alternations():
        assert alternation == list(CREDENTIAL_QUERY_STEMS)


@pytest.mark.parametrize("name", generated_names())
def test_every_name_the_class_generates_is_redacted_at_the_edge(name: str) -> None:
    """`delete key` covered the four names the API refuses and nothing else. A caller who
    guesses `?api_key=` gets a 422 and leaves the key in the log, which is REG-V3's incident
    one field along. The names are generated from the stem list, not chosen to match."""
    for logged in redacted_at_the_edge(name):
        assert "OWNERKEY" not in logged, f"?{name}= reaches the access log in full"
        assert "limit=5" in logged, f"?{name}= redaction ate the rest of the query"


@pytest.mark.parametrize("name", LOGGED_IN_FULL_ONCE)
def test_every_name_that_once_reached_a_log_in_full_is_redacted(name: str) -> None:
    for logged in redacted_at_the_edge(name):
        assert "OWNERKEY" not in logged, f"?{name}= reaches the access log in full again"


def test_the_served_parameters_stay_readable_except_the_declared_over_redaction() -> None:
    """A log that redacts the request's own parameters has stopped being a record of what was
    asked. The served names come from the OpenAPI document, so a new one is measured; the
    ones the class eats are declared, so the set cannot grow silently."""
    eaten = {
        name
        for name in served_query_names()
        if any(f"{name}=OWNERKEY" not in logged for logged in redacted_at_the_edge(name))
    }

    assert eaten == OVER_REDACTED_SERVED


@pytest.mark.parametrize(
    "name", [*generated_names(), *served_query_names(), *LOGGED_IN_FULL_ONCE]
)
def test_the_edge_and_the_origin_redact_the_same_names(name: str) -> None:
    """The API's own filter is the second line for anything that reaches uvicorn. Both derive
    from one stem list and read a stem anywhere in the name, so they agree in both directions:
    the edge is never the looser of the two, and never eats a name the origin keeps."""
    line = f"/v1/wells?{name}=OWNERKEY&limit=5"
    at_the_origin = "OWNERKEY" not in redact(line)

    for logged in redacted_at_the_edge(name):
        assert ("OWNERKEY" not in logged) == at_the_origin, f"?{name}= differs edge to origin"


def test_no_log_block_declares_one_field_twice() -> None:
    """Caddy's `fields` is a map: a second entry for a field replaces the first silently, so
    two filters on `request>uri` ship as whichever the adapter read last."""
    for names in fields_entries():
        duplicates = sorted({name for name in names if names.count(name) > 1})
        assert not duplicates, f"a later filter silently replaces an earlier one: {duplicates}"


def test_both_listeners_redact_their_uri_the_same_way() -> None:
    assert len({(pattern.pattern, value) for pattern, value in uri_regexps()}) == 1
