#!/usr/bin/env bash
# The checks that matter, positive and negative, runnable at any time on VM 111.
# Reads the owner key from /etc/glasswell/app.env and never prints it.
set -uo pipefail

INFRA_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# The API has no TCP listener; `api_curl` dials the socket and $API is only the authority curl
# needs to build a URL. It stays a http:// prefix so ${url/#$API/$SITE} still finds it.
API_SOCKET=/run/glasswell/api.sock
API=http://localhost
MARTIN=http://127.0.0.1:3000
SITE_HOST=glasswell.lab.rpx.sh
SITE="https://$SITE_HOST"
CADDY_BIN=/usr/local/bin/caddy
CADDY_LOG=/var/log/caddy/access.log
CERT_MIN_DAYS=20
WEB_ROOT=/opt/glasswell/web
DEPLOY_SRC=/opt/glasswell/src
DATA_ROOT=/data
LAN_ADDRESS=192.168.2.111
PG_TUNING="$INFRA_DIR/postgres/postgresql.conf.d/glasswell.conf"
PSQL=(sudo -u postgres psql -d glasswell -tAc)
VENV_PY=/opt/glasswell/venv/bin/python
UNIT_DIR=/etc/systemd/system
STATUS_SNAPSHOT=/var/lib/glasswell/status.json

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

# `systemctl show -p Result` answers `success` for a unit that is absent or has never run, so the
# run evidence is asserted separately from the verdict.
last_run_state() {
    local load started
    load="$(systemctl show "$1" -p LoadState --value)"
    started="$(systemctl show "$1" -p ExecMainStartTimestamp --value)"
    if [[ $load != loaded ]]; then
        printf '%s\n' "$load"
    elif [[ -z $started ]]; then
        printf 'never-ran\n'
    else
        printf 'ran\n'
    fi
}

listening_on() { ss -ltn | grep -q "$1"; }
glob_matches() { compgen -G "$1" >/dev/null; }
api_curl() { curl --unix-socket "$API_SOCKET" "$@"; }

valid_status_snapshot() {
    "$VENV_PY" -c \
        'import json, pathlib, sys; value = json.loads(pathlib.Path(sys.argv[1]).read_text()); sys.exit(0 if isinstance(value, dict) else 1)' \
        "$STATUS_SNAPSHOT" >/dev/null 2>&1
}

status_snapshot_omits_private_environment() {
    "$VENV_PY" - "$STATUS_SNAPSHOT" /etc/glasswell/db.env /etc/glasswell/app.env \
        >/dev/null 2>&1 <<'PY'
import pathlib
import sys

snapshot = pathlib.Path(sys.argv[1]).read_text()
private_markers = ("KEY", "TOKEN", "SECRET", "PASSWORD", "DSN", "DATABASE_URL", "_ROOT", "MARTIN_URL")
for env_path in sys.argv[2:]:
    for raw_line in pathlib.Path(env_path).read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip().strip("'\"")
        if len(value) >= 8 and any(marker in name.upper() for marker in private_markers):
            if value in snapshot:
                raise SystemExit(1)
PY
}

status_api_serves_current_snapshot() {
    api_curl -sf --max-time 20 -H "X-Glasswell-Key: $owner_key" "$API/v1/status" \
        | "$VENV_PY" -c \
            'import json, sys; data = json.load(sys.stdin)["data"]; checks = data["checks"]; jobs = data["jobs"]; failed = any(item["state"] in {"degraded", "unavailable"} for item in checks) or any(item["state"] == "degraded" for item in jobs); raise SystemExit(0 if data["snapshot_state"] == "current" and data["observed_at"] and data["datasets"] and not failed else 1)' \
        >/dev/null 2>&1
}

printf 'services\n'
for unit in glasswell-api martin postgresql caddy; do
    assert "$unit active" active "$(systemctl is-active "$unit")"
done

printf 'status snapshot\n'
assert "glasswell-status.timer enabled" enabled "$(systemctl is-enabled glasswell-status.timer)"
assert "glasswell-status.timer active" active "$(systemctl is-active glasswell-status.timer)"
assert "glasswell-lineage-retention.timer enabled" enabled \
    "$(systemctl is-enabled glasswell-lineage-retention.timer)"
assert "glasswell-lineage-retention.timer active" active \
    "$(systemctl is-active glasswell-lineage-retention.timer)"
assert "glasswell-lineage-retention.service has run" ran \
    "$(last_run_state glasswell-lineage-retention.service)"
assert "glasswell-lineage-retention.service last result" success \
    "$(systemctl show glasswell-lineage-retention.service -p Result --value)"
backup_enabled="$(systemctl is-enabled glasswell-backup.timer 2>/dev/null)"
restore_enabled="$(systemctl is-enabled glasswell-restore-drill.timer 2>/dev/null)"
assert "restore-drill timer follows backup enablement" "$backup_enabled" "$restore_enabled"
if [[ $backup_enabled == enabled ]]; then
    assert "glasswell-backup.timer active" active "$(systemctl is-active glasswell-backup.timer)"
    assert "glasswell-restore-drill.timer active" active \
        "$(systemctl is-active glasswell-restore-drill.timer)"
else
    ok "backup and restore-drill timers are intentionally disabled"
fi
assert "glasswell-status.service has run" ran \
    "$(last_run_state glasswell-status.service)"
assert "glasswell-status.service last result" success \
    "$(systemctl show glasswell-status.service -p Result --value)"
assert_true "status snapshot is a regular file" "missing at $STATUS_SNAPSHOT" \
    test -f "$STATUS_SNAPSHOT"
assert_false "status snapshot is not a symlink" "$STATUS_SNAPSHOT must be a regular owned file" \
    test -L "$STATUS_SNAPSHOT"
if [[ -f $STATUS_SNAPSHOT && ! -L $STATUS_SNAPSHOT ]]; then
    assert "status snapshot ownership" "glasswell:glasswell" \
        "$(stat -c '%U:%G' "$STATUS_SNAPSHOT")"
    snapshot_mode="$(stat -c '%a' "$STATUS_SNAPSHOT")"
    assert_true "status snapshot mode is private ($snapshot_mode)" "expected 600 or 640" \
        test "$snapshot_mode" = 600 -o "$snapshot_mode" = 640
    assert_true "status snapshot is a JSON object" "invalid JSON or non-object root" \
        valid_status_snapshot
    assert_true "status snapshot omits private environment values" \
        "credential, internal URL, DSN, or configured filesystem path bytes were found" \
        status_snapshot_omits_private_environment
fi

# The roster is the tree's, not a list here: a glasswell-* unit added to infra/systemd but not
# to install.sh's placement loop is never installed, and a timer that was never installed is a
# monthly capture that silently never runs (M1-9). Equality, not existence — the live file
# drifting from the tree is the v0.21 saga.
printf 'units\n'
for unit in "$INFRA_DIR"/systemd/glasswell-*.service "$INFRA_DIR"/systemd/glasswell-*.timer; do
    name="${unit##*/}"
    assert_true "$name installed and identical to the tree" "missing or drifted at $UNIT_DIR" \
        cmp -s "$unit" "$UNIT_DIR/$name"
done

printf 'api\n'
neighbor_subjects="$("${PSQL[@]}" "select count(*) from marts.nd_neighbor_subjects")"
neighbor_edges="$("${PSQL[@]}" "select count(*) from marts.nd_neighbor_edges")"
assert_true "ND neighbour subjects populated ($neighbor_subjects)" "mart is empty" \
    test "${neighbor_subjects:-0}" -gt 0
assert_true "ND neighbour edges populated ($neighbor_edges)" "mart is empty" \
    test "${neighbor_edges:-0}" -gt 0
assert "GET /healthz" 200 "$(api_curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API/healthz")"
assert "GET /v1 without a key is refused" 403 \
    "$(api_curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API/v1/wells?limit=1")"
assert "GET /v1 with a wrong key is refused" 403 \
    "$(api_curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
        -H 'X-Glasswell-Key: not-the-owner-key' "$API/v1/wells?limit=1")"

owner_key="$(sed -n 's/^GLASSWELL_OWNER_KEY=//p' /etc/glasswell/app.env)"
if [[ -z $owner_key ]]; then
    bad "owner key present in app.env" "GLASSWELL_OWNER_KEY is empty"
else
    ok "owner key present in app.env"
    assert "GET /v1/wells with the owner key" 200 \
        "$(api_curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
            -H "X-Glasswell-Key: $owner_key" "$API/v1/wells?limit=1")"
    assert "GET /v1/health with the owner key" 200 \
        "$(api_curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
            -H "X-Glasswell-Key: $owner_key" "$API/v1/health")"
    assert "GET /v1/status with the owner key after collection" 200 \
        "$(api_curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
            -H "X-Glasswell-Key: $owner_key" "$API/v1/status")"
    assert_true "GET /v1/status serves a current non-empty snapshot" \
        "API rejected, omitted, or marked the freshly collected snapshot stale" \
        status_api_serves_current_snapshot
    # B-1: a query string reaches the access log verbatim, so a key is refused there.
    assert "a key in the query string is refused" 422 \
        "$(api_curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
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
assert "GET / serves the app" 200 "$(api_curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API/")"
# DR-57: there is no SPA fallback, so /changelog/ resolves only if the file is really there.
# The header stamp links to it from every screen, which makes a 404 here a visible one.
assert_true "the changelog page is deployed" "no changelog/index.html" \
    test -f "$WEB_ROOT/changelog/index.html"
assert "GET /changelog/ serves the release notes" 200 \
    "$(api_curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API/changelog/")"

printf 'tiles\n'
assert "martin /health" 200 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$MARTIN/health")"
catalog="$(curl -s --max-time 10 "$MARTIN/catalog")"
# The roster is the code's, not a list here: a layer added to TILE_LAYERS and installed by
# install_tile_functions must reach the catalogue, and a stale list here would say it had.
expected_layers="$("$VENV_PY" -c 'from glasswell.marts.tiles import TILE_LAYERS
print(" ".join(sorted(layer.name for layer in TILE_LAYERS)))' 2>/dev/null)"  # a venv that cannot import the marts yields an empty roster, and the asserts below say so
for layer in $expected_layers; do
    assert_true "martin publishes $layer" "absent from /catalog" \
        grep -q "\"$layer\"" <<<"$catalog"
done

# DR-05: with the config adopted the catalogue is exactly the allowlist. Until then martin
# auto-publishes eleven sources, three of them staging relations, and this reads FAIL — the
# same honest signal the tuning block gave before deployer step 5.
published="$(python3 -c 'import json,sys; print(" ".join(sorted(json.load(sys.stdin)["tiles"])))' \
    <<<"$catalog" 2>/dev/null)"  # a martin that answered nothing parses to nothing, and the assert below says so
assert "martin publishes the allowlist and nothing else" "$expected_layers" "$published"

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
    read -r tile_status tile_bytes < <(api_curl -s -o /dev/null \
        -w '%{http_code} %{size_download}' --max-time 20 \
        -H "X-Glasswell-Key: $owner_key" "$tile_url")
    assert "tile $zoom/$tile_x/$tile_y status" 200 "$tile_status"
    assert_true "tile carries $tile_bytes bytes" "zero bytes" test "${tile_bytes:-0}" -gt 0
fi

# M-1: martin auto-publishes staging, so the proxy's allowlist is the control that holds
# "staging never serves". The catalogue still lists the layer; the product API must not serve it.
assert "a staging layer through the proxy is refused" 404 \
    "$(api_curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
        -H "X-Glasswell-Key: $owner_key" "$API/v1/tiles/nd_gis_wells/8/54/89.pbf")"

# DIR-13. The edge is checked through the name a browser uses, pinned to this host so a
# resolver answering something else reads as a failure rather than as a pass elsewhere.
printf 'tls\n'
resolve=(--resolve "$SITE_HOST:443:127.0.0.1" --resolve "$SITE_HOST:80:127.0.0.1")

if [[ -x $CADDY_BIN ]]; then
    assert_true "caddy carries the cloudflare DNS module" "DNS-01 renewal cannot work without it" \
        grep -qx 'dns.providers.cloudflare' <<<"$("$CADDY_BIN" list-modules)"
else
    bad "caddy binary at $CADDY_BIN" "missing — see infra/caddy/README.md"
fi

# No -k anywhere here: a certificate curl will not accept is the failure this section exists for.
assert "GET $SITE serves the app" 200 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "${resolve[@]}" "$SITE/")"
assert "http://$SITE_HOST/ redirects" 308 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "${resolve[@]}" "http://$SITE_HOST/")"
assert "the redirect target is the https origin" "$SITE/" \
    "$(curl -s -o /dev/null -w '%{redirect_url}' --max-time 10 "${resolve[@]}" "http://$SITE_HOST/")"

served_cert="$(openssl s_client -connect 127.0.0.1:443 -servername "$SITE_HOST" </dev/null 2>/dev/null | openssl x509 2>/dev/null)"  # a handshake that fails prints its reason to stderr and no PEM; the empty check below is the report
if [[ -z $served_cert ]]; then
    bad "the endpoint serves a certificate" "no PEM came back from 127.0.0.1:443"
else
    ok "the endpoint serves a certificate"
    issuer="$(openssl x509 -noout -issuer <<<"$served_cert")"
    assert_true "issued by Let's Encrypt" "issuer is ${issuer#issuer=}" \
        grep -q "Let's Encrypt" <<<"$issuer"
    assert_true "the certificate names $SITE_HOST" "it is not in subjectAltName" \
        grep -q "DNS:$SITE_HOST" <<<"$(openssl x509 -noout -ext subjectAltName <<<"$served_cert")"
    not_after="$(openssl x509 -noout -enddate <<<"$served_cert")"
    remaining=$(( ($(date -d "${not_after#*=}" +%s) - $(date +%s)) / 86400 ))
    # Caddy renews at 30 days remaining, so anything under 20 means renewal has been failing
    # for over a week — the alarm DIR-13 asks for, ten days before a browser would notice.
    assert_true "over $CERT_MIN_DAYS days of certificate left ($remaining)" \
        "renewal is failing; check journalctl -u caddy for the ACME error" \
        test "$remaining" -gt "$CERT_MIN_DAYS"
fi

edge_headers="$(curl -s -D - -o /dev/null --max-time 15 "${resolve[@]}" "$SITE/" | tr -d '\r')"
# N-6 plus DIR-13: the origin owns these, so a `header` directive in the Caddyfile would add a
# second value rather than replace the first. Two copies is the defect this counts.
for header in x-content-type-options x-frame-options referrer-policy x-robots-tag \
              content-security-policy; do
    assert "exactly one $header through the edge" 1 "$(grep -ci "^$header:" <<<"$edge_headers")"
done
assert_true "the origin sees the request as https" \
    "no upgrade-insecure-requests in the CSP: X-Forwarded-Proto is not reaching uvicorn" \
    grep -qi 'content-security-policy:.*upgrade-insecure-requests' <<<"$edge_headers"

encoding_of() {
    curl -s -D - -o /dev/null --max-time 30 "${resolve[@]}" \
        -H 'Accept-Encoding: gzip, zstd' -H "X-Glasswell-Key: $owner_key" "$1" \
        | tr -d '\r' | sed -n 's/^[Cc]ontent-[Ee]ncoding: //p' | paste -sd, -
}
bundle="$(compgen -G "$WEB_ROOT/assets/index-*.js" | head -1)"
if [[ -n $bundle ]]; then
    assert "the bundle through the edge is gzipped once" gzip "$(encoding_of "$SITE/assets/${bundle##*/}")"
fi
if [[ -n ${tile_url:-} ]]; then
    # martin's zstd rides through the proxy untouched; Caddy re-encoding it would show two.
    assert "a tile through the edge carries martin's encoding and no other" zstd \
        "$(encoding_of "${tile_url/#$API/$SITE}")"
fi

assert_true "caddy's admin api is loopback-only" "not bound to 127.0.0.1:2019" \
    listening_on '127.0.0.1:2019'
if [[ -n $owner_key ]]; then
    # Send both shapes a key can take before reading the log back, so this cannot pass for
    # want of traffic: the header the API accepts, and the query string it refuses and an
    # edge would otherwise write down verbatim.
    assert "a key in the query string is refused at the edge" 422 \
        "$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "${resolve[@]}" \
            --get --data-urlencode "key=$owner_key" "$SITE/v1/health")"
    assert "a keyed request through the edge is served" 200 \
        "$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "${resolve[@]}" \
            -H "X-Glasswell-Key: $owner_key" "$SITE/v1/health")"
    if [[ -r $CADDY_LOG ]]; then
        assert_false "the owner key is absent from caddy's access log" "found in $CADDY_LOG" \
            grep -q -- "$owner_key" "$CADDY_LOG"
    else
        bad "caddy's access log is readable" "$CADDY_LOG — run this as root"
    fi
fi

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
assert_true "the api socket exists" "no socket at $API_SOCKET" test -S "$API_SOCKET"
assert_true "the api answers on its socket" "no answer on $API_SOCKET" \
    api_curl -sf -o /dev/null --max-time 10 "$API/healthz"
# uvicorn chmods the socket 0666, so the directory is the access control and this is the check
# that says so. glasswell owns it, caddy's group traverses it, nobody else gets in.
assert "the api socket directory is caddy-only" "glasswell caddy 750" \
    "$(stat -c '%U %G %a' "${API_SOCKET%/*}")"
assert_false "the api holds no TCP listener" "still bound to 127.0.0.1:8000 — uvicorn moved to $API_SOCKET" \
    listening_on '127.0.0.1:8000'
assert_false "api is not on the LAN" "still bound to 0.0.0.0:8000 — the pre-DIR-13 bind" \
    listening_on '0.0.0.0:8000'
assert_true "caddy listens on the LAN" "nothing is bound to :443" listening_on ':443'
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
# Without the stamp, lineage code_version falls back to pkg:0.1.0 (v0.30 saga).
assert_true "code-version.env carries a code identity" \
    "no GLASSWELL_CODE_VERSION — deploy.sh step 5c stamps it" \
    grep -qs '^GLASSWELL_CODE_VERSION=.' /etc/glasswell/code-version.env  # -s: a missing file is the failure the assert reports, not a grep diagnostic
api_rw="$(systemctl show glasswell-api -p ReadWritePaths --value)"
assert_false "api cannot write the raw zone" "ReadWritePaths carries /data/raw" \
    grep -q '/data/raw' <<<"$api_rw"

printf '\n%d passed, %d failed\n' "$passed" "$failed"
[[ $failed -eq 0 ]]
