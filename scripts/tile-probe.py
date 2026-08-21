#!/usr/bin/env python3
"""Measure the tile and basemap paths over the transport a browser actually negotiates.

curl does the fetching on purpose: a Python HTTP client measures Python's stack, not the
TLS-terminated, keep-alive, HTTP/2 path the map runs over. This process only builds the
argument list, parses `--write-out`, and reports percentiles.

    tile-probe.py range   --base https://host --count 40 --size 65536
    tile-probe.py burst   --base https://host --count 40 --concurrency 8
    tile-probe.py tile    --base https://host --key-file k.curl --tile nd_laterals/7/27/44
    tile-probe.py revalidate --base https://host --key-file k.curl --tile nd_laterals/7/27/44

The key never appears in an argument list, an environment variable or this program's
output: `--key-file` is a 0600 `curl -K` config and is passed to curl by path.
"""

from __future__ import annotations

import argparse
import math
import random
import statistics
import subprocess
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

WRITE_OUT = (
    "%{http_code} %{size_download} %{time_starttransfer}"
    " %{time_total} %header{content-encoding}\n"
)
ARCHIVE_PATH = "/basemap/basemap.pmtiles"
DEFAULT_SPAN = 336_000_000


@dataclass(frozen=True)
class Sample:
    code: int
    bytes: int
    ttfb_ms: float
    total_ms: float
    encoding: str


@dataclass(frozen=True)
class Summary:
    label: str
    n: int
    codes: str
    bytes_med: float
    ttfb_med: float
    ttfb_p95: float
    total_med: float
    total_p95: float
    total_max: float

    def render(self) -> str:
        return (
            f"{self.label:<40} n={self.n:<4} {self.codes:<9} bytes={self.bytes_med:>9,.0f}"
            f"  ttfb med={self.ttfb_med:7.2f} p95={self.ttfb_p95:7.2f}"
            f"  total med={self.total_med:7.2f} p95={self.total_p95:7.2f} max={self.total_max:7.2f}"
        )


def range_offsets(count: int, size: int, span: int, seed: int) -> list[tuple[int, int]]:
    """Reproducible pseudo-random reads: a re-run has to sample the same offsets to compare."""
    rng = random.Random(seed)
    highest = max(0, span - size)
    offsets = []
    for _ in range(count):
        start = rng.randrange(highest + 1)
        offsets.append((start, start + size - 1))
    return offsets


def parse_line(line: str) -> Sample:
    # An absent Content-Encoding leaves no token at all, so the field count is 4 or 5.
    code, size, ttfb, total, *encoding = line.split()
    return Sample(
        code=int(code),
        bytes=int(size),
        ttfb_ms=float(ttfb) * 1000,
        total_ms=float(total) * 1000,
        encoding=encoding[0] if encoding else "",
    )


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)
    return ordered[max(0, index)]


def summarise(label: str, samples: Sequence[Sample]) -> Summary:
    if not samples:
        return Summary(label, 0, "-", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    ttfb = [s.ttfb_ms for s in samples]
    total = [s.total_ms for s in samples]
    return Summary(
        label=label,
        n=len(samples),
        codes=",".join(str(c) for c in sorted({s.code for s in samples})),
        bytes_med=statistics.median(s.bytes for s in samples),
        ttfb_med=statistics.median(ttfb),
        ttfb_p95=percentile(ttfb, 0.95),
        total_med=statistics.median(total),
        total_p95=percentile(total, 0.95),
        total_max=max(total),
    )


def curl_command(
    urls: Sequence[str],
    http_version: str,
    key_file: str | None,
    headers: Sequence[str],
    ranges: Sequence[tuple[int, int]] | None,
) -> list[str]:
    command = ["curl", "-s", f"--http{http_version}"]
    if key_file:
        command += ["-K", key_file]
    for header in headers:
        command += ["-H", header]
    for index, url in enumerate(urls):
        if ranges is not None:
            start, end = ranges[index]
            command += ["-r", f"{start}-{end}"]
        command += ["-o", "/dev/null", "-w", WRITE_OUT, url]
    return command


def run(command: Sequence[str]) -> list[Sample]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return [parse_line(line) for line in result.stdout.splitlines() if line.strip()]


def _suite_range(args: argparse.Namespace) -> Summary:
    ranges = range_offsets(args.count, args.size, args.span, args.seed)
    urls = [args.base + args.path] * args.count
    samples = run(curl_command(urls, args.http, args.key_file, args.header, ranges))
    return summarise(args.label or f"range {args.size}B h{args.http}", samples)


def _suite_burst(args: argparse.Namespace) -> Summary:
    ranges = range_offsets(args.count, args.size, args.span, args.seed)
    lanes: list[list[tuple[int, int]]] = [[] for _ in range(args.concurrency)]
    for index, span in enumerate(ranges):
        lanes[index % args.concurrency].append(span)
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = pool.map(
            lambda lane: run(
                curl_command(
                    [args.base + args.path] * len(lane), args.http, args.key_file, args.header, lane
                )
            ),
            lanes,
        )
        samples = [sample for lane in results for sample in lane]
    return summarise(args.label or f"burst x{args.concurrency} {args.size}B h{args.http}", samples)


def _suite_tile(args: argparse.Namespace) -> Summary:
    url = f"{args.base}/v1/tiles/{args.tile}.pbf"
    samples = run(curl_command([url] * args.count, args.http, args.key_file, args.header, None))
    return summarise(args.label or f"tile {args.tile} h{args.http}", samples)


def _suite_revalidate(args: argparse.Namespace) -> Summary:
    url = f"{args.base}/v1/tiles/{args.tile}.pbf"
    config = ["-K", args.key_file] if args.key_file else []
    head = subprocess.run(
        ["curl", "-s", "-D", "-", "-o", "/dev/null", *config, url],
        capture_output=True,
        text=True,
        check=False,
    )
    etag = ""
    for line in head.stdout.splitlines():
        if line.lower().startswith("etag:"):
            etag = line.split(":", 1)[1].strip()
    if not etag:
        print("no ETag on the tile response; revalidation cannot be measured", file=sys.stderr)
        return summarise(args.label or "revalidate", [])
    headers = (*args.header, f"If-None-Match: {etag}")
    samples = run(curl_command([url] * args.count, args.http, args.key_file, headers, None))
    return summarise(args.label or f"revalidate {args.tile} h{args.http}", samples)


SUITES = {
    "range": _suite_range,
    "burst": _suite_burst,
    "tile": _suite_tile,
    "revalidate": _suite_revalidate,
}


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=sorted(SUITES))
    parser.add_argument("--base", default="https://glasswell.lab.rpx.sh")
    parser.add_argument("--path", default=ARCHIVE_PATH)
    parser.add_argument("--tile", default="nd_laterals/7/27/44")
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--size", type=int, default=65536)
    parser.add_argument("--span", type=int, default=DEFAULT_SPAN)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--http", default="2", choices=["1.1", "2", "3"])
    parser.add_argument("--key-file", default=None)
    parser.add_argument("--header", action="append", default=[])
    parser.add_argument("--label", default="")
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    print(SUITES[args.suite](args).render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
