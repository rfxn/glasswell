"""`scripts/tile-probe.py` is the tool the tile-latency claims in this repository come from.

Its numbers are only worth citing if the sampling is deterministic and the summary is the
statistic it says it is, so both are pinned here. The transport itself (curl) is not
exercised — the tool shells out on purpose, so that a measurement runs over the same HTTP
stack a browser negotiates rather than over a Python client's idea of one.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "tile-probe.py"


def _load():
    spec = importlib.util.spec_from_file_location("tile_probe", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: @dataclass resolves its own module out of sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = _load()


def test_offsets_are_deterministic_for_a_seed():
    first = probe.range_offsets(count=8, size=4096, span=1_000_000, seed=7)
    second = probe.range_offsets(count=8, size=4096, span=1_000_000, seed=7)
    assert first == second
    assert first != probe.range_offsets(count=8, size=4096, span=1_000_000, seed=8)


def test_offsets_stay_inside_the_archive():
    for start, end in probe.range_offsets(count=64, size=4096, span=10_000, seed=1):
        assert start >= 0
        assert end < 10_000
        assert end - start + 1 == 4096


def test_a_measurement_line_parses_into_its_fields():
    sample = probe.parse_line("206 65536 0.002471 0.002761 zstd")
    assert sample.code == 206
    assert sample.bytes == 65536
    assert sample.ttfb_ms == pytest.approx(2.471)
    assert sample.total_ms == pytest.approx(2.761)
    assert sample.encoding == "zstd"


def test_an_identity_response_parses_when_curl_writes_no_encoding_field():
    """`%header{content-encoding}` expands to nothing at all, not to a placeholder."""
    assert probe.parse_line("200 12 0.001 0.002 ").encoding == ""
    assert probe.parse_line("200 12 0.001 0.002").encoding == ""


def test_percentile_picks_a_real_observation():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert probe.percentile(values, 0.5) == 5.0
    assert probe.percentile(values, 0.95) == 10.0
    assert probe.percentile([4.0], 0.95) == 4.0


def test_summary_reports_every_status_code_it_saw():
    samples = [
        probe.parse_line("200 10 0.001 0.002 -"),
        probe.parse_line("304 0 0.001 0.002 -"),
        probe.parse_line("200 10 0.001 0.002 -"),
    ]
    summary = probe.summarise("mixed", samples)
    assert summary.codes == "200,304"
    assert summary.n == 3


def test_summary_of_no_samples_does_not_divide_by_zero():
    summary = probe.summarise("empty", [])
    assert summary.n == 0
    assert summary.total_med == 0.0
    assert "empty" in summary.render()


def test_the_curl_command_carries_one_request_per_url():
    command = probe.curl_command(
        ["https://example.test/a", "https://example.test/b"],
        http_version="2",
        key_file=None,
        headers=(),
        ranges=None,
    )
    assert command.count("https://example.test/a") == 1
    assert command.count("https://example.test/b") == 1
    assert "--http2" in command
    assert command.count(probe.WRITE_OUT) == 2


def test_the_curl_command_pairs_each_range_with_its_url():
    command = probe.curl_command(
        ["https://example.test/archive"] * 2,
        http_version="1.1",
        key_file=None,
        headers=(),
        ranges=[(0, 15), (64, 79)],
    )
    assert command.index("0-15") < command.index("64-79")
    assert "--http1.1" in command


def test_the_key_file_is_passed_by_reference_never_by_value():
    command = probe.curl_command(
        ["https://example.test/v1/tiles/x/1/2/3.pbf"],
        http_version="2",
        key_file="/run/secret.curl",
        headers=("Accept-Encoding: zstd",),
        ranges=None,
    )
    assert "-K" in command
    assert "/run/secret.curl" in command
    assert not any("X-Glasswell-Key" in part for part in command)
