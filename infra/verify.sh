#!/usr/bin/env bash
# The checks that matter, positive and negative, runnable at any time on VM 111.
# Reads the owner key from /etc/glasswell/app.env and never prints it.
set -uo pipefail

API=http://127.0.0.1:8000
MARTIN=http://127.0.0.1:3000
WEB_ROOT=/opt/glasswell/web
LAN_ADDRESS=192.168.2.111
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
fi

printf 'frontend\n'
assert_true "index.html present" "missing" test -f "$WEB_ROOT/index.html"
assert_true "hashed bundle present" "no assets/index-*.js" \
    glob_matches "$WEB_ROOT/assets/index-*.js"
assert "GET / serves the app" 200 "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API/")"

printf 'tiles\n'
assert "martin /health" 200 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$MARTIN/health")"
catalog="$(curl -s --max-time 10 "$MARTIN/catalog")"
for layer in nd_laterals nd_wells; do
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

printf 'exposure\n'
assert_true "martin is loopback-only" "not bound to 127.0.0.1:3000" listening_on '127.0.0.1:3000'
assert_true "api listens on the LAN" "not bound to 0.0.0.0:8000" listening_on '0.0.0.0:8000'
assert_false "postgres is not on the LAN" "listening on $LAN_ADDRESS:5432" \
    listening_on "$LAN_ADDRESS:5432"
assert_true "ufw active" "inactive" systemctl is-active --quiet ufw

printf 'secrets and sandbox\n'
assert "app.env ownership and mode" "root:root 600" "$(stat -c '%U:%G %a' /etc/glasswell/app.env)"
api_rw="$(systemctl show glasswell-api -p ReadWritePaths --value)"
assert_false "api cannot write the raw zone" "ReadWritePaths carries /data/raw" \
    grep -q '/data/raw' <<<"$api_rw"

printf '\n%d passed, %d failed\n' "$passed" "$failed"
[[ $failed -eq 0 ]]
