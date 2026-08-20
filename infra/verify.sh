#!/usr/bin/env bash
# The checks that matter, positive and negative, runnable at any time on VM 111.
# Reads the owner key from /etc/glasswell/app.env and never prints it.
set -uo pipefail

INFRA_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
API=http://127.0.0.1:8000
MARTIN=http://127.0.0.1:3000
WEB_ROOT=/opt/glasswell/web
DEPLOY_SRC=/opt/glasswell/src
DATA_ROOT=/data
LAN_ADDRESS=192.168.2.111
PG_TUNING="$INFRA_DIR/postgres/postgresql.conf.d/glasswell.conf"
PSQL=(sudo -u postgres psql -d glasswell -tAc)

passed=0
failed=0

ok() { printf '  ok   %s\n' "$1"; passed=$((passed + 1)); }
bad() { printf '  FAIL %s — %s\n' "$1" "$2"; failed=$((failed + 1)); }

assert() {
    local label="$1" expected="$2" actual="$3"
    if [[ $actual == "$expected" ]]; then
        ok "$label"
    else
        bad "$label" "expected $expected, got $actual"
    fi
}

assert_true() {
    local label="$1" detail="$2"
    shift 2
    if "$@"; then
        ok "$label"
    else
        bad "$label" "$detail"
    fi
}

assert_false() {
    local label="$1" detail="$2"
    shift 2
    if "$@"; then
        bad "$label" "$detail"
    else
        ok "$label"
    fi
}

listening_on() { ss -ltn | grep -q "$1"; }
glob_matches() { compgen -G "$1" >/dev/null; }

printf 'services\n'
for unit in glasswell-api martin postgresql; do
    assert "$unit active" active "$(systemctl is-active "$unit")"
done

printf 'api\n'
assert "GET /healthz" 200 "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API/healthz")"
assert "GET /v1 without a key is refused" 403 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API/v1/wells?limit=1")"
assert "GET /v1 with a wrong key is refused" 403 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
        -H 'X-Glasswell-Key: not-the-owner-key' "$API/v1/wells?limit=1")"

owner_key="$(sed -n 's/^GLASSWELL_OWNER_KEY=//p' /etc/glasswell/app.env)"
if [[ -z $owner_key ]]; then
    bad "owner key present in app.env" "GLASSWELL_OWNER_KEY is empty"
else
    ok "owner key present in app.env"
    assert "GET /v1/wells with the owner key" 200 \
        "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
            -H "X-Glasswell-Key: $owner_key" "$API/v1/wells?limit=1")"
    assert "GET /v1/health with the owner key" 200 \
        "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
            -H "X-Glasswell-Key: $owner_key" "$API/v1/health")"
    # B-1: a query string reaches the access log verbatim, so a key is refused there.
    assert "a key in the query string is refused" 422 \
        "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
            --get --data-urlencode "key=$owner_key" "$API/v1/health")"
    assert_false "the owner key is absent from the journal" "found in glasswell-api's journal" \
        journalctl -u glasswell-api --no-pager -q --grep "$owner_key"
fi

printf 'frontend\n'
assert_true "index.html present" "missing" test -f "$WEB_ROOT/index.html"
assert_true "hashed bundle present" "no assets/index-*.js" \
    glob_matches "$WEB_ROOT/assets/index-*.js"
# M-6: the source is proprietary and StaticFiles serves whatever is in the webroot.
assert_false "no source map is deployed" "assets/*.js.map is published" \
    glob_matches "$WEB_ROOT/assets/*.map"
assert "GET / serves the app" 200 "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API/")"

printf 'tiles\n'
assert "martin /health" 200 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$MARTIN/health")"
catalog="$(curl -s --max-time 10 "$MARTIN/catalog")"
for layer in nd_laterals nd_wells nd_spacing_units; do
    assert_true "martin publishes $layer" "absent from /catalog" \
        grep -q "\"$layer\"" <<<"$catalog"
done

# The tile is derived from a real feature, never hard-coded: a bounding-box corner tile can
# legitimately be empty, and martin answers 204 for that (PLAN.md B9 / P5's correction).
read -r zoom tile_x tile_y < <("${PSQL[@]}" "
  select 8,
         floor((ST_X(p) + 180) / 360 * 256)::int,
         floor((1 - ln(tan(radians(ST_Y(p))) + 1 / cos(radians(ST_Y(p)))) / pi()) / 2 * 256)::int
    from (select ST_PointOnSurface(geom) p from marts.nd_laterals_tile limit 1) feature" \
  | tr '|' ' ')
if [[ -z ${zoom:-} ]]; then
    bad "feature-derived tile" "marts.nd_laterals_tile is empty"
else
    tile_url="$API/v1/tiles/nd_laterals/$zoom/$tile_x/$tile_y.pbf"
    read -r tile_status tile_bytes < <(curl -s -o /dev/null \
        -w '%{http_code} %{size_download}' --max-time 20 \
        -H "X-Glasswell-Key: $owner_key" "$tile_url")
    assert "tile $zoom/$tile_x/$tile_y status" 200 "$tile_status"
    assert_true "tile carries $tile_bytes bytes" "zero bytes" test "${tile_bytes:-0}" -gt 0
fi

# M-1: martin auto-publishes staging, so the proxy's allowlist is the control that holds
# "staging never serves". The catalogue still lists the layer; the product API must not serve it.
assert "a staging layer through the proxy is refused" 404 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
        -H "X-Glasswell-Key: $owner_key" "$API/v1/tiles/nd_gis_wells/8/54/89.pbf")"

# DR-06: SB-07 2.3's zones under the volume that exists. install.sh creates them.
printf 'zones\n'
for zone in raw staging scratch; do
    assert_true "$DATA_ROOT/$zone exists" "run install.sh" test -d "$DATA_ROOT/$zone"
done

# DR-28: the deploy is `git archive HEAD | tar -x`, which cannot carry a git-excluded file.
# Anything here is a leftover of the rsync era, and docs/product-*.md is carve-out material.
printf 'deploy hygiene\n'
stray=""
for pattern in CLAUDE.md 'PLAN*.md' AUDIT.md MEMORY.md docs work-output .claude .rdf; do
    for path in $(compgen -G "$DEPLOY_SRC/$pattern"); do stray+="${path##*/} "; done
done
assert "no git-excluded working file on the deploy root" "" "${stray% }"

printf 'exposure\n'
assert_true "martin is loopback-only" "not bound to 127.0.0.1:3000" listening_on '127.0.0.1:3000'
assert_true "api listens on the LAN" "not bound to 0.0.0.0:8000" listening_on '0.0.0.0:8000'
assert_false "postgres is not on the LAN" "listening on $LAN_ADDRESS:5432" \
    listening_on "$LAN_ADDRESS:5432"
assert_true "ufw active" "inactive" systemctl is-active --quiet ufw

# Driven by the shipped drop-in so the check cannot drift from the file it verifies.
# Red until the deployer runs install.sh --with-postgres and restarts PostgreSQL (DR-20).
printf 'postgres tuning\n'
if [[ -r $PG_TUNING ]]; then
    while IFS= read -r line; do
        setting="${line%% =*}"
        assert "$setting" "${line##*= }" "$("${PSQL[@]}" "show $setting")"
    done < <(grep -E '^[a-z_]+ = ' "$PG_TUNING")
else
    bad "postgres tuning" "$PG_TUNING is missing, so nothing was checked"
fi

printf 'secrets and sandbox\n'
assert "app.env ownership and mode" "root:root 600" "$(stat -c '%U:%G %a' /etc/glasswell/app.env)"
api_rw="$(systemctl show glasswell-api -p ReadWritePaths --value)"
assert_false "api cannot write the raw zone" "ReadWritePaths carries /data/raw" \
    grep -q '/data/raw' <<<"$api_rw"

printf '\n%d passed, %d failed\n' "$passed" "$failed"
[[ $failed -eq 0 ]]
