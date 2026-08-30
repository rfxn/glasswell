#!/usr/bin/env bash
# Publish Cloudflare's edge ranges to /etc/glasswell/cloudflare-ips.txt.
#
# The list is a misconfiguration detector, never a trust decision, so this script's job is to
# refuse a bad publish rather than to guarantee a fresh one. A shrunken or unparseable answer
# leaves the previous file in place; verify.sh reports staleness separately.

set -uo pipefail

SOURCE_URL="${GLASSWELL_CF_IPS_URL:-https://api.cloudflare.com/client/v4/ips}"
TARGET="${GLASSWELL_CF_RANGES:-/etc/glasswell/cloudflare-ips.txt}"
GROUP="${GLASSWELL_GROUP:-glasswell}"
MINIMUM_CIDRS=10

fail() {
    printf 'refresh-ranges: %s\n' "$1" >&2
    exit 1
}

command -v curl >/dev/null 2>&1 || fail "curl is not on PATH"  # probe output is not wanted
command -v python3 >/dev/null 2>&1 || fail "python3 is not on PATH"  # probe output is not wanted

work="$(mktemp -d)" || fail "cannot create a work directory"
# The trap is the only cleanup path: every failure below exits rather than falling through.
trap 'command rm -rf "$work"' EXIT

payload="$work/payload.json"
if ! curl -fsS --max-time 30 "$SOURCE_URL" -o "$payload"; then
    fail "fetch failed from $SOURCE_URL"
fi

candidate="$work/cloudflare-ips.txt"
{
    printf '# Cloudflare edge ranges, published by glasswell-cf-ranges.service.\n'
    printf '# source: %s\n' "$SOURCE_URL"
    printf '# fetched: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$candidate" || fail "cannot write $candidate"

if ! python3 - "$payload" >> "$candidate" <<'PY'
import ipaddress
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    document = json.load(handle)
if not document.get("success"):
    raise SystemExit("the API reported success=false")
result = document["result"]
entries = list(result.get("ipv4_cidrs", [])) + list(result.get("ipv6_cidrs", []))
for entry in entries:
    ipaddress.ip_network(entry, strict=False)
    print(entry)
PY
then
    fail "the payload did not parse as a CIDR list"
fi

count="$(grep -cE '^[^#]' "$candidate")"
if [[ -z $count || $count -lt $MINIMUM_CIDRS ]]; then
    fail "refusing to publish $count ranges (fewer than $MINIMUM_CIDRS): keeping $TARGET"
fi

target_dir="$(dirname "$TARGET")"
command mkdir -p "$target_dir" || fail "cannot create $target_dir"
command install -o root -g "$GROUP" -m 0644 "$candidate" "$TARGET" \
    || fail "cannot publish $TARGET"

printf 'refresh-ranges: published %s ranges to %s\n' "$count" "$TARGET"
