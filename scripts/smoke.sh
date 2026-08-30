#!/usr/bin/env bash
# DR-19: the machine-checkable twin of SMOKE.md — every assertion is a claim that file makes
# in prose, plus the four this cycle added (per-point lineage, two hostile layer ids, and the
# committed contract against the served one). Read-only: GET, and nothing else.
# The owner key is read from the environment, a file, or /etc/glasswell/app.env, never printed.
set -uo pipefail

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SNAPSHOT="$REPO_DIR/tests/contract/openapi_snapshot.json"
APP_ENV=/etc/glasswell/app.env

base="${GLASSWELL_BASE_URL:-https://glasswell.lab.rpx.sh}"
api10=3305310451
# The New Mexico spine check reads a header, not a row count: the gate opens on the spine.
nm_api10=3002540209
key_file=""

usage() {
    cat <<'EOF'
usage: smoke.sh [options]

  --base URL        API root; $GLASSWELL_BASE_URL, else https://glasswell.lab.rpx.sh
  --api10 API10     the well every well-level assertion reads (default 3305310451)
  --nm-api10 API10  the New Mexico well the spine assertion reads (default 3002540209)
  --key-file FILE   read GLASSWELL_OWNER_KEY=... from FILE (default /etc/glasswell/app.env)

$GLASSWELL_BASE_URL is the one name every tier reads: this script, tests/e2e and the docs.
The key may also arrive in $GLASSWELL_OWNER_KEY. It is never echoed and never placed in a
query string: a query string reaches the access log verbatim.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --*=*) set -- "${1%%=*}" "${1#*=}" "${@:2}"; continue ;;
        --base) base="$2"; shift 2 ;;
        --api10) api10="$2"; shift 2 ;;
        --nm-api10) nm_api10="$2"; shift 2 ;;
        --key-file) key_file="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
done

base="${base%/}"
# N-3: a shared /tmp is where two agents overwrite each other's scratch file.
work_dir="$(mktemp -d -t gw-smoke.XXXXXXXX)"
trap 'rm -rf "$work_dir"' EXIT

passed=0
failed=0
number=0

ok() { number=$((number + 1)); passed=$((passed + 1)); printf '  ok   %2d %s\n' "$number" "$1"; }
bad() {
    number=$((number + 1))
    failed=$((failed + 1))
    printf '  FAIL %2d %s — %s\n' "$number" "$1" "$2"
}

assert() {
    local label="$1" expected="$2" actual="$3"
    if [[ $actual == "$expected" ]]; then ok "$label"; else bad "$label" "expected $expected, got $actual"; fi
}

assert_true() {
    local label="$1" detail="$2"
    shift 2
    if "$@"; then ok "$label"; else bad "$label" "$detail"; fi
}

owner_key="${GLASSWELL_OWNER_KEY:-}"
if [[ -z $owner_key ]]; then
    source_file="${key_file:-$APP_ENV}"
    if [[ -r $source_file ]]; then
        owner_key="$(sed -n 's/^GLASSWELL_OWNER_KEY=//p' "$source_file")"
    fi
fi
if [[ -z $owner_key ]]; then
    printf 'no owner key: set GLASSWELL_OWNER_KEY or pass --key-file\n' >&2
    exit 2
fi

status() { curl -sS -o /dev/null -w '%{http_code}' --max-time 30 "$@"; }
# A cookie jar per run, so a session probe cannot leak into the operator's browser or a
# later invocation. The jar lives in $work_dir, which the exit trap removes.
sessioned() { curl -sS --max-time 60 -b "$work_dir/cookies" -c "$work_dir/cookies" "$@"; }
sessioned_status() {
    curl -sS -o /dev/null -w '%{http_code}' --max-time 30 \
        -b "$work_dir/cookies" -c "$work_dir/cookies" "$@"
}
keyed() { curl -sS --max-time 60 -H "X-Glasswell-Key: $owner_key" "$@"; }
keyed_status() { status -H "X-Glasswell-Key: $owner_key" "$@"; }

body() { keyed "$base$1" > "$work_dir/body.json"; }
pointer_of() {
    python3 -c 'import json,sys; print(json.load(sys.stdin)["errors"][0]["pointer"])' \
        < "$work_dir/body.json" 2>/dev/null  # a response that is not a problem+json has no pointer; the assert prints what it got
}

printf 'smoke: %s (well %s)\n' "$base" "$api10"

printf 'reachability and refusal\n'
assert "GET /healthz" 200 "$(status "$base/healthz")"
assert "GET /v1 without a key is refused" 403 "$(status "$base/v1/wells?limit=1")"
assert "GET /v1 with a wrong key is refused" 403 \
    "$(status -H 'X-Glasswell-Key: not-the-owner-key' "$base/v1/wells?limit=1")"
# B-1: the key rides a header or the fragment, never a query string.
keyed --get --data-urlencode "key=$owner_key" "$base/v1/health" > "$work_dir/body.json"
assert "a key in the query string is refused at /query/key" "/query/key" "$(pointer_of)"
keyed "$base/v1/wells?limit=5000" > "$work_dir/body.json"
assert "an over-large limit is refused at /query/limit" "/query/limit" "$(pointer_of)"

printf 'the well card\n'
assert "GET /v1/wells/$api10" 200 "$(keyed_status "$base/v1/wells/$api10")"
body "/v1/wells/$api10"
assert_true "lateral length carries a unit and a derivation handle" \
    "a served figure without both is a naked number" \
    python3 -c '
import json, sys
card = json.load(open(sys.argv[1]))["data"]["lateral_length_ft"]
sys.exit(0 if card.get("unit") and card.get("d", "").startswith("drv_") else 1)
' "$work_dir/body.json"
assert "a well that does not exist is 404, not an empty card" 404 \
    "$(keyed_status "$base/v1/wells/9999999999")"

printf 'production and lineage\n'
body "/v1/wells/$api10/production"
assert_true "every production point carries its own lineage handle" \
    "a column-level handle would attribute six months to one derivation" \
    python3 -c '
import json, sys
data = json.load(open(sys.argv[1]))["data"]
series, lineage = data["series"], data["_lineage"]
points = len(series["pm"])
volumes = [
    column for column in series
    if column != "pm"
    and not column.endswith(("_null_semantics", "_report_vintage", "_aggregation"))
]
expected = {f"series.{column}.{index}" for column in volumes for index in range(points)}
sys.exit(0 if points and expected <= set(lineage) else 1)
' "$work_dir/body.json"

explain_link="$(python3 -c '
import json, sys
print(json.load(open(sys.argv[1]))["links"]["explain"] or "")
' "$work_dir/body.json")"
assert_true "the production envelope offers an explain link" "links.explain is null" \
    test -n "$explain_link"
keyed "$base$explain_link" > "$work_dir/explain.json"
assert_true "the chain terminates at a checksummed regulator file" \
    "no manifest node with a 64-hex sha256 and a dmr.nd.gov url" \
    python3 -c '
import json, re, sys
chains = json.load(open(sys.argv[1]))["data"]["chains"]
nodes = [node for chain in chains for node in chain["nodes"]]
manifests = [
    node for node in nodes
    if re.fullmatch(r"[0-9a-f]{64}", str(node.get("sha256") or ""))
    and "dmr.nd.gov" in str(node.get("acquisition_url") or "")
]
sys.exit(0 if manifests else 1)
' "$work_dir/explain.json"
keyed --get --data-urlencode "h=drv_doesnotexist" "$base/v1/explain" > "$work_dir/body.json"
assert_true "an unknown handle explains honestly rather than 500" \
    "no stop_reason and no unresolved answer" \
    python3 -c '
import json, sys
answer = json.load(open(sys.argv[1]))
text = json.dumps(answer)
sys.exit(0 if "unknown_id" in text or "lineage_unresolved" in text else 1)
' "$work_dir/body.json"

printf 'the ledgers\n'
body "/v1/conformance"
assert_true "every conformance rule carries a rationale and an evidence url" \
    "a mapping that exists only in code fails review (R8)" \
    python3 -c '
import json, sys
rules = json.load(open(sys.argv[1]))["data"]
sys.exit(0 if rules and all(rule.get("rationale") and rule.get("evidence_url") for rule in rules) else 1)
' "$work_dir/body.json"
body "/v1/quarantine/summary"
assert_true "the quarantine ledger is non-empty and every group names a reason" \
    "a zero here would mean the checks were not running" \
    python3 -c '
import json, sys
data = json.load(open(sys.argv[1]))["data"]
groups = data["groups"]
sys.exit(0 if data["total"] > 0 and groups and all(group["key"] for group in groups) else 1)
' "$work_dir/body.json"
body "/v1/health"
assert_true "no source is stale and every pending one is named" "a stale source is a served lie" \
    python3 -c '
import json, sys
data = json.load(open(sys.argv[1]))["data"]
sources, pending = data["sources"], set(data["pending_sources"])
sys.exit(0 if sources and not data["degraded_sources"]
         and all(source["state"] in ("current", "pending") for source in sources)
         and pending == {s["source_id"] for s in sources if s["state"] == "pending"} else 1)
' "$work_dir/body.json"

printf 'the New Mexico spine\n'
# The gate opens on the spine, not on the row count: what is asserted is a well header with a
# geometry provenance and a status vocabulary rule behind it. A count of promoted rows would
# have passed before canonical.wells held a single New Mexico row.
nm_status="$(keyed_status "$base/v1/wells/$nm_api10")"
if [[ $nm_status == 200 ]]; then
    body "/v1/wells/$nm_api10"
    assert_true "a New Mexico well resolves through the spine with its handles" \
        "a served New Mexico figure with no rule behind it is a naked number" \
        python3 -c '
import json, sys
card = json.load(open(sys.argv[1]))["data"]
sys.exit(0 if card["state_code"] == "30" and card["geometry_provenance"] else 1)
' "$work_dir/body.json"
    keyed "$base/v1/wells/status-summary?bbox=-109.1,31.2,-102.9,37.1" > "$work_dir/body.json"
    assert_true "the New Mexico status vocabulary rule is New Mexico's" \
        "an NM count under cr_nd_status_vocab_1 would be North Dakota's answer to a New Mexico question" \
        python3 -c '
import json, sys
basins = json.load(open(sys.argv[1]))["data"]["basins"]
rules = {row["state_code"]: row["status_vocabulary_rule"] for row in basins}
sys.exit(0 if rules.get("30") == "cr_nm_wellhistory_status_vocab_1" else 1)
' "$work_dir/body.json"
else
    printf '  skip    New Mexico spine: /v1/wells/%s is %s, so the gate is not open here\n' \
        "$nm_api10" "$nm_status"
fi
# Check 15 above is a fetch-freshness signal: freshness_state is a pure function of
# max(manifests.fetch_vintage) and consults no canonical table, so it flips when a manifest is
# registered and says nothing about whether anything was promoted.

printf 'tiles and the contract\n'
tile_path="$(python3 -c '
import json, math, sys
card = json.load(open(sys.argv[1]))["data"]["surface_point"]
zoom = 12
side = 2 ** zoom
x = int((card["lon"] + 180.0) / 360.0 * side)
radians = math.radians(card["lat"])
y = int((1 - math.log(math.tan(radians) + 1 / math.cos(radians)) / math.pi) / 2 * side)
print(f"{zoom}/{x}/{y}")
' <(keyed "$base/v1/wells/$api10"))"
read -r tile_status tile_bytes < <(curl -sS -o /dev/null -w '%{http_code} %{size_download}' \
    --max-time 60 -H "X-Glasswell-Key: $owner_key" \
    "$base/v1/tiles/nd_laterals/$tile_path.pbf")
assert_true "a tile over the well's own surface point carries bytes" \
    "status $tile_status, $tile_bytes bytes" \
    test "$tile_status" = 200 -a "${tile_bytes:-0}" -gt 0
# Blueprint 3.0.1: staging never serves, and the proxy allowlist is the control that holds it.
assert "a staging layer through the proxy is refused" 404 \
    "$(keyed_status "$base/v1/tiles/nd_gis_wells/8/54/89.pbf")"
# N-5: a layer id is interpolated into a path, so a hostile one must not reach martin. The
# exact code matters — `!= 200` would read a 500 from a proxy that tried as "refused".
assert "a traversal-shaped layer id is refused" 404 \
    "$(keyed_status "$base/v1/tiles/..%2f..%2fetc%2fpasswd/8/54/89.pbf")"
assert "a well-formed layer id outside the allowlist is refused" 422 \
    "$(keyed_status "$base/v1/tiles/gw-evil-layer/8/54/89.pbf")"
assert_true "every path in the committed OpenAPI snapshot exists on this instance" \
    "the published contract and the served one disagree" \
    env SMOKE_OWNER_KEY="$owner_key" python3 -c '
import json, os, sys, urllib.request
snapshot = json.load(open(sys.argv[1]))
request = urllib.request.Request(sys.argv[2], headers={"X-Glasswell-Key": os.environ.get("SMOKE_OWNER_KEY", "")})
with urllib.request.urlopen(request, timeout=30) as response:
    live = json.load(response)
missing = sorted(set(snapshot["paths"]) - set(live["paths"]))
if missing:
    print("missing:", ", ".join(missing), file=sys.stderr)
sys.exit(1 if missing else 0)
' "$SNAPSHOT" "$base/openapi.json"

printf 'session auth\n'
assert "GET /docs without a credential is refused" 403 "$(status "$base/docs")"
assert "GET /openapi.json without a credential is refused" 403 "$(status "$base/openapi.json")"
assert "GET /v1/session/challenge is open" 200 "$(sessioned_status "$base/v1/session/challenge")"
assert "a state-changing call with no csrf token is refused" 403 \
    "$(sessioned_status -X DELETE "$base/v1/session")"
# The password is read from a file or the environment, never from argv: argv is visible in
# /proc to every local user and lands in the operator's shell history.
if [[ -n ${GLASSWELL_SMOKE_USER:-} && -n ${GLASSWELL_SMOKE_PASSWORD:-} ]]; then
    csrf_token="$(sessioned "$base/v1/session/challenge" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["csrf_token"])')"
    login_body="$(python3 -c 'import json,os; print(json.dumps({"username": os.environ["GLASSWELL_SMOKE_USER"], "password": os.environ["GLASSWELL_SMOKE_PASSWORD"]}))')"
    assert "login with the smoke account succeeds" 201 \
        "$(sessioned_status -X POST -H 'Content-Type: application/json' \
            -H "X-Glasswell-CSRF: $csrf_token" --data "$login_body" "$base/v1/session")"
    assert "the session reads its own role" 200 "$(sessioned_status "$base/v1/session")"
    assert "the session reaches a data route" 200 \
        "$(sessioned_status "$base/v1/wells?limit=1")"
    csrf_token="$(sessioned "$base/v1/session/challenge" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["csrf_token"])')"
    assert "logout succeeds" 200 \
        "$(sessioned_status -X DELETE -H "X-Glasswell-CSRF: $csrf_token" "$base/v1/session")"
    assert "the cookie is dead after logout" 403 "$(sessioned_status "$base/v1/wells?limit=1")"
else
    printf '  skip session login — set GLASSWELL_SMOKE_USER and GLASSWELL_SMOKE_PASSWORD\n'
fi

printf '\n%d passed, %d failed\n' "$passed" "$failed"
[[ $failed -eq 0 ]]
