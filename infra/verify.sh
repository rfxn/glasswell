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
SBIN_DIR=/usr/local/sbin
STATUS_SNAPSHOT=/var/lib/glasswell/status.json
RESTORE_RESULT=/var/lib/glasswell-restore-drill/result.json
OFFSITE_RECEIPT=/var/lib/glasswell-backup/offsite.json
RECOVERY_RESULT=/var/lib/glasswell-recovery-drill/result.json
PGDUMP_DIR=/data/backups/pg
# Both bounds mirror status/collector.py; tests/unit/test_durability_verifier.py pins them equal.
RESTORE_PROOF_MAX_AGE_DAYS=8
OFFSITE_RECEIPT_MAX_AGE_DAYS=2
PUBLIC_HOST=glasswell.rpx.sh
CLOUDFLARED_DIR=/etc/cloudflared
CADDY_FILE=/etc/caddy/Caddyfile
SCHEDULER_ENV=/etc/glasswell/scheduler.env
SCHEDULER_UNIT=glasswell-scheduler.service
PG_IDENT_DROPIN=/etc/postgresql/16/main/pg_ident.d/glasswell.conf
PG_IDENT_MAP=glasswell
CF_RANGES=/etc/glasswell/cloudflare-ips.txt
# Lab DNS is split-horizon and NXDOMAINs the public record, so the host cannot resolve the
# name its own edge answers on. Probes carry the address instead of pinning it in /etc/hosts.
PUBLIC_RESOLVER=1.1.1.1

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

# The tunnel listener exists only where a tunnel is configured, so its *existence* is not a
# safety property and must not be asserted as one: unconditional, this reported "8080 is bound
# off-loopback" on a host with nothing bound to 8080 at all, which is not merely a failure but
# a false statement about the host. The claim worth holding is the conditional one -- whatever
# is bound to 8080 must be bound to loopback -- and it is assertable on every host, public or
# not. The negative needs no condition at all: "not on every interface" is true when nothing is
# listening, so it stays unconditional and keeps proving the property before the exposure.
assert_tunnel_listener_bind() {
    if listening_on ':8080'; then
        assert_true "the caddy tunnel listener is loopback-only" "8080 is bound off-loopback" \
            listening_on '127.0.0.1:8080'
    else
        ok "no tunnel listener is bound: nothing is listening on 8080"
    fi
    assert_false "the caddy tunnel listener is not on every interface" "8080 is on 0.0.0.0" \
        listening_on '0.0.0.0:8080'
}
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

# The three durability receipts share a shape: a JSON object carrying `result` and a UTC
# `completed_at`. One reader serves all of them; `field` accepts a dotted path.
receipt_field() {
    "$VENV_PY" - "$1" "$2" 2>/dev/null <<'PY'  # 2>/dev/null: an unreadable receipt prints nothing and the assert that reads it reports the miss; a traceback would bury the failing line
import json
import pathlib
import sys

value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
for part in sys.argv[2].split("."):
    if not isinstance(value, dict):
        raise SystemExit(1)
    value = value.get(part)
print("" if value is None else json.dumps(value).strip('"'))
PY
}

receipt_freshness() {
    "$VENV_PY" - "$1" "$2" 2>/dev/null <<'PY'  # 2>/dev/null: same contract as receipt_field — an empty verdict fails the assert that reads it
import json
import pathlib
import sys
from datetime import UTC, datetime, timedelta

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
completed = datetime.fromisoformat(payload["completed_at"].replace("Z", "+00:00")).astimezone(UTC)
age = datetime.now(UTC) - completed
if age < -timedelta(minutes=5):
    verdict = "future"
elif age > timedelta(days=int(sys.argv[2])):
    verdict = "stale"
else:
    verdict = "fresh"
print(f"{max(0, int(age.total_seconds() // 3600))} {verdict}")
PY
}

# root:glasswell 0640 from a root-owned state directory is the contract every durability
# receipt is published under, so the product user can read a proof it cannot forge.
assert_receipt_is_safe() {
    local label="$1" path="$2"
    assert_true "$label is a regular file" "missing at $path" test -f "$path"
    assert_false "$label is not a symlink" "$path must be a regular owned file" test -L "$path"
    if [[ -f $path && ! -L $path ]]; then
        assert "$label ownership and mode" "root:glasswell 640" "$(stat -c '%U:%G %a' "$path")"
    fi
}

# Newest by mtime, which is the same rule glasswell-restore-drill.sh selects a dump by, so the
# generation this compares against is the one the drill would have picked.
newest_dump_generation() {
    local candidate newest="" newest_stamp=0 stamp
    shopt -s nullglob
    for candidate in "$PGDUMP_DIR"/glasswell-*.manifest.json; do
        stamp="$(stat -c %Y -- "$candidate")" || continue
        if (( stamp > newest_stamp )); then
            newest_stamp=$stamp
            newest=${candidate##*/}
        fi
    done
    shopt -u nullglob
    newest="${newest#glasswell-}"
    printf '%s\n' "${newest%.manifest.json}"
}

# The drill is weekly and the live head moves on every migration deploy, so a deploy that lands
# a migration legitimately leaves the receipt one head behind until the next Sunday run. Compare
# heads only once a drill has completed since the newest migration was applied; `schema_match`,
# the safety checks and the freshness bound stay unconditional either way.
restore_proof_covers_live_head() {
    local applied_at completed_at
    applied_at="$("${PSQL[@]}" "select coalesce(max(applied_at), 'epoch'::timestamptz) from public.schema_migrations")" \
        || return 1
    [[ -n $applied_at ]] || return 1
    applied_at="$(date -d "$applied_at" +%s)" || return 1
    completed_at="$(receipt_field "$RESTORE_RESULT" completed_at)"
    [[ -n $completed_at ]] || return 1
    completed_at="$(date -d "$completed_at" +%s)" || return 1
    (( completed_at > applied_at ))
}

# A deploy that lands the receipt-publishing backup script is legitimately receipt-less until
# that night's run. Once a backup has run *since* the script was installed the receipt is
# mandatory, so a deleted or abandoned one fails from then on.
offsite_receipt_expected() {
    local script="$SBIN_DIR/glasswell-backup.sh" installed_at last_run
    installed_at="$(stat -c %Y -- "$script")" || return 1
    last_run="$(systemctl show glasswell-backup.service -p ExecMainExitTimestamp --value)"
    [[ -n $last_run ]] || return 1
    last_run="$(date -d "$last_run" +%s)" || return 1
    (( last_run > installed_at ))
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

# Timer enablement says the drill is scheduled, not that it proved anything. The drill pins no
# schema version — it restores whichever manifest is newest by mtime — so without the head
# comparison below a drill that passed against a dump several migrations behind the running app
# reads green, and a receipt that silently stopped updating reads green with it.
printf 'restore drill proof\n'
if [[ $backup_enabled == enabled ]]; then
    assert_receipt_is_safe "restore proof" "$RESTORE_RESULT"
    if [[ -f $RESTORE_RESULT && ! -L $RESTORE_RESULT ]]; then
        assert "restore drill result" passed "$(receipt_field "$RESTORE_RESULT" result)"
        assert "restore drill schema heads agree" true \
            "$(receipt_field "$RESTORE_RESULT" schema_match)"
        if restore_proof_covers_live_head; then
            assert "restore proof schema head equals the live head" \
                "$("${PSQL[@]}" "select coalesce(max(version), 0) from public.schema_migrations")" \
                "$(receipt_field "$RESTORE_RESULT" restored_schema_version)"
        else
            ok "restore proof predates the newest migration — the next weekly drill refreshes it"
        fi
        assert "restore proof scratch cleanup" true \
            "$(receipt_field "$RESTORE_RESULT" scratch_removed)"
        read -r restore_age_hours restore_verdict < <(receipt_freshness \
            "$RESTORE_RESULT" "$RESTORE_PROOF_MAX_AGE_DAYS")
        assert "restore proof freshness (${restore_age_hours:-?}h, bound ${RESTORE_PROOF_MAX_AGE_DAYS}d)" \
            fresh "${restore_verdict:-unreadable}"
    fi
else
    ok "restore proof not expected while the restore-drill timer is intentionally disabled"
fi

# The forge grant is `rrsync -wo` — write-only. VM 111 can push and cannot list, stat or read
# back the far side, so nothing here is a round-trip proof. These assert what the *sender* did
# and when. The generation equality is what catches a receipt that stopped updating.
printf 'offsite copy\n'
# `install` resets the script's mtime on every deploy, so the readiness test excuses only an
# *absent* receipt. A receipt that exists is asserted whatever the mtimes say — otherwise a
# deleted, failed or stale one would be invisible for 24 h after each deploy.
if [[ $backup_enabled == enabled ]] && { [[ -e $OFFSITE_RECEIPT ]] || offsite_receipt_expected; }; then
    assert_receipt_is_safe "offsite receipt" "$OFFSITE_RECEIPT"
    if [[ -f $OFFSITE_RECEIPT && ! -L $OFFSITE_RECEIPT ]]; then
        assert "offsite push result" passed "$(receipt_field "$OFFSITE_RECEIPT" result)"
        assert "offsite receipt states its send-side limit" send_side_only \
            "$(receipt_field "$OFFSITE_RECEIPT" verification)"
        assert "offsite receipt covers the newest local dump generation" \
            "$(newest_dump_generation)" "$(receipt_field "$OFFSITE_RECEIPT" generation)"
        assert "offsite push carried the generation's dump bytes" true \
            "$(receipt_field "$OFFSITE_RECEIPT" dump_bytes_covered)"
        read -r offsite_age_hours offsite_verdict < <(receipt_freshness \
            "$OFFSITE_RECEIPT" "$OFFSITE_RECEIPT_MAX_AGE_DAYS")
        assert "offsite receipt freshness (${offsite_age_hours:-?}h, bound ${OFFSITE_RECEIPT_MAX_AGE_DAYS}d)" \
            fresh "${offsite_verdict:-unreadable}"
    fi
elif [[ $backup_enabled == enabled ]]; then
    ok "no offsite receipt expected yet — the backup script is newer than its last run"
else
    ok "offsite receipt not expected while the backup timer is intentionally disabled"
fi

# Replacement-VM recovery is mechanised and has never been executed. Absence of a receipt is
# reported, not failed: hard-failing on a proof nobody can produce yet would red this verifier
# permanently and block every deploy behind it.
printf 'replacement-vm recovery\n'
assert_true "the recovery drill is installed" "missing at $SBIN_DIR/glasswell-recovery-drill.sh" \
    test -x "$SBIN_DIR/glasswell-recovery-drill.sh"
if [[ -e $RECOVERY_RESULT ]]; then
    assert_receipt_is_safe "recovery proof" "$RECOVERY_RESULT"
    assert "recovery drill result" passed "$(receipt_field "$RECOVERY_RESULT" result)"
    assert "recovery proof schema heads agree" true \
        "$(receipt_field "$RECOVERY_RESULT" schema_match)"
else
    ok "recovery drill is mechanised but has NEVER been executed (no receipt at $RECOVERY_RESULT)"
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

# DR-H5. The loop above walks the tree, so a unit that exists only on the host is invisible to
# it — which is how an enabled, armed glasswell-repromote.timer sat undeclared for nine days.
# This is the other direction: every glasswell-* unit on the host must be declared in the tree.
for unit in "$UNIT_DIR"/glasswell-*.service "$UNIT_DIR"/glasswell-*.timer; do
    [[ -e $unit ]] || continue
    name="${unit##*/}"
    assert_true "$name is declared in the tree" \
        "installed at $UNIT_DIR but absent from infra/systemd — declare it or remove it" \
        test -e "$INFRA_DIR/systemd/$name"
done

printf 'api\n'
neighbor_subjects="$("${PSQL[@]}" "select count(*) from marts.nd_neighbor_subjects")"
neighbor_edges="$("${PSQL[@]}" "select count(*) from marts.nd_neighbor_edges")"
assert_true "ND neighbour subjects populated ($neighbor_subjects)" "mart is empty" \
    test "${neighbor_subjects:-0}" -gt 0
assert_true "ND neighbour edges populated ($neighbor_edges)" "mart is empty" \
    test "${neighbor_edges:-0}" -gt 0
# P5-R5. The registry ships its rows in 073 and `seed_all` re-asserts them on every deploy, so
# an unregistered tile layer means one of the two did not land. It is not a cosmetic gap:
# canonical.status_resolution joins the resolved NM registration, so with no row New Mexico's
# statuses resolve to nothing and the map draws it unmapped rather than refusing.
unregistered_layers="$("${PSQL[@]}" "select coalesce(string_agg(layer, ', ' order by layer), '')
  from (select replace(table_name, '_tile', '') as layer
          from information_schema.tables
         where table_schema = 'marts' and table_name like '%\_wells\_tile') t
 where not exists (
    select 1 from lineage.jurisdictions_as_of(current_date, current_date) j
     where j.wells_tile_layer_id = t.layer)")"
assert "every wells tile layer has a resolved jurisdiction registration" "" "$unregistered_layers"
# The other half of the same defect class, and the one no other check can see. A jurisdiction
# whose status vocabulary resolves at read time serves its class out of
# lineage.status_resolution_resolved; the refresh skips a registration whose mapping table has
# not landed, because aborting would take a migration or the deploy's seed down with it. A skip
# that lasts -- a mapping_table misspelt in a rule spec, or a map renamed by a later migration --
# draws that jurisdiction's whole spine unmapped and self-heals never. /v1/status serves the same
# fact as its `status_resolver` check; this is the one that catches it six months later.
unresolved_read_time="$("${PSQL[@]}" "select coalesce(string_agg(
        j.identity_prefix || ' ' || j.jurisdiction_code || ' wants lineage.' ||
        (c.spec->>'mapping_table'), ', ' order by j.identity_prefix), '')
  from lineage.jurisdictions_as_of(current_date, current_date) j
  join lineage.jurisdiction_rules r
    on r.jurisdiction_code = j.jurisdiction_code
   and r.effective_from = j.effective_from
   and r.published_at = j.published_at
   and r.decision = 'status_vocabulary'
   and r.serving
  join lineage.conformance_rules c on c.rule_id = r.rule_id
 where j.identity_prefix is not null
   and c.spec->>'resolved_at' = 'read_time'
   and not exists (select 1 from lineage.status_resolution_resolved s
                    where s.for_state_code = j.identity_prefix)")"
assert "every read-time status vocabulary has resolver rows" "" "$unresolved_read_time"
cumulatives="$("${PSQL[@]}" "select count(*) from marts.well_cumulatives")"
withholding="$("${PSQL[@]}" "select count(*) from marts.well_withholding")"
assert_true "per-well cumulatives populated ($cumulatives)" "mart is empty" \
    test "${cumulatives:-0}" -gt 0
# Three states, one query, same discipline as the design check below: the mart is written by
# the cumulatives refresh, so before that has ever run an empty table says nothing about the
# system, and after it has run an empty table is only a fault if there were open withheld rows
# to hold. Refusing unconditionally asserted that NDIC still withholds something.
withholding_state="$("${PSQL[@]}" "select case
    when (select count(*) from lineage.derivations
           where operation = 'mart.refresh'
             and output_dataset = 'marts.well_cumulatives') = 0 then 'pending'
    when (select count(*) from marts.well_withholding) > 0 then 'ok'
    when (select count(*) from lineage.quarantine_rows
           where reason_code = 'confidential_withheld' and state = 'open') = 0 then 'none_open'
    else 'bad' end")"
case "$withholding_state" in
    pending)
        ok "well withholding not yet refreshed — no mart.refresh has run on this host" ;;
    none_open)
        ok "well withholding empty — no open confidential_withheld row to hold" ;;
    *)
        assert_true "well withholding populated ($withholding)" \
            "the refresh has run and open confidential_withheld rows exist, but the mart is empty" \
            test "$withholding_state" = "ok" ;;
esac
# Conditional, and this is the one honest exception: a host that has never fetched the 440 MB
# voluntary-disclosure archive has no design rows to hold, and refusing its deploy would be
# asserting a fact about the source rather than about the system. The condition is one query,
# so the check cannot drift from its premise.
design_state="$("${PSQL[@]}" "select case
    when (select count(*) from staging.fracfocus_disclosures
           where state_name = 'North Dakota' or api_number like '33%') = 0 then 'pending'
    when (select count(*) from canonical.well_completion_design) > 0 then 'ok'
    else 'bad' end")"
if [ "$design_state" = "pending" ]; then
    printf '  .. completion design pending — no ND FracFocus disclosure is staged on this host\n'
else
    assert_true "completion design promoted" "ND disclosures are staged but none promoted" \
        test "$design_state" = "ok"
fi
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
print(" ".join(sorted(layer.name for layer in TILE_LAYERS)))' 2>/dev/null)"  # the status below separates an import failure from an empty roster
roster_read=$?
# Both sides of the equality below are built by a suppressed command, so an empty roster and
# an empty catalogue compare equal and read ok. Neither emptiness is a pass (F27).
if (( roster_read != 0 )); then
    bad "martin publishes the allowlist and nothing else" \
        "the venv could not import TILE_LAYERS, so nothing was compared"
elif [[ -z $expected_layers ]]; then
    bad "martin publishes the allowlist and nothing else" \
        "TILE_LAYERS imported but is empty, so the roster asserts nothing"
fi
for layer in $expected_layers; do
    assert_true "martin publishes $layer" "absent from /catalog" \
        grep -q "\"$layer\"" <<<"$catalog"
done

# DR-05: with the config adopted the catalogue is exactly the allowlist. Until then martin
# auto-publishes eleven sources, three of them staging relations, and this reads FAIL — the
# same honest signal the tuning block gave before deployer step 5.
published="$(python3 -c 'import json,sys; print(" ".join(sorted(json.load(sys.stdin)["tiles"])))' \
    <<<"$catalog" 2>/dev/null)"  # the status below separates an unparseable body from an empty tiles list
catalog_read=$?
if (( catalog_read != 0 )); then
    bad "martin publishes the allowlist and nothing else" \
        "martin returned no parseable catalogue, so nothing was compared"
elif [[ -z $published ]]; then
    bad "martin publishes the allowlist and nothing else" \
        "martin's catalogue parsed but publishes no tiles at all"
elif [[ -n $expected_layers ]]; then
    assert "martin publishes the allowlist and nothing else" "$expected_layers" "$published"
fi

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
    while IFS= read -r path; do
        [[ -n $path ]] || continue
        stray+="${path##*/} "
    done < <(compgen -G "$DEPLOY_SRC/$pattern")
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
# Red between a drop-in revision and the restart that applies it (infra/README.md step 5).
printf 'postgres tuning\n'
if [[ -r $PG_TUNING ]]; then
    checked=0
    while IFS= read -r line; do
        line="${line%%#*}"                    # an inline comment is not part of the value
        setting="${line%% =*}"
        read -r expected <<<"${line#* = }"    # read trims what stripping the comment left
        assert "$setting" "$expected" "$("${PSQL[@]}" "show $setting")"
        checked=$((checked + 1))
    done < <(grep -E '^[a-z0-9_]+ = ' "$PG_TUNING")
    # F28: a drop-in reformatted to key=value matches nothing, and silence would read as a pass.
    assert_true "the drop-in yielded settings to check ($checked)" \
        "no '<setting> = <value>' line matched in $PG_TUNING" test "$checked" -gt 0
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

printf 'session auth\n'
assert "an anonymous /v1 request is refused" 403 \
    "$(api_curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API/v1/wells?limit=1")"
# 403, not 404: the document routes are registered before the SPA mount, so they answer the
# gate rather than being shadowed by it. A 404 here means the mount ordering regressed.
assert "an anonymous /docs is refused" 403 \
    "$(api_curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API/docs")"
assert "an anonymous /openapi.json is refused" 403 \
    "$(api_curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API/openapi.json")"
assert "the challenge route answers without a credential" 200 \
    "$(api_curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API/v1/session/challenge")"
owner_accounts="$("${PSQL[@]}" "select count(*) from lineage.users where role = 'owner' and disabled_at is null")"
assert_true "at least one enabled owner account exists ($owner_accounts)" \
    "no owner account: run glasswell-owner-bootstrap" \
    test "${owner_accounts:-0}" -gt 0
default_accounts="$("${PSQL[@]}" "select count(*) from lineage.users where username in ('admin', 'glasswell', 'owner', 'root')")"
assert "no default credential shipped" 0 "${default_accounts:-1}"
assert_false "app.env sets no anonymous flag" "GLASSWELL_ALLOW_ANON=1 is uncommented" \
    grep -q '^GLASSWELL_ALLOW_ANON=1' /etc/glasswell/app.env
assert_true "app.env carries a csrf key" "GLASSWELL_CSRF_KEY is short or absent" \
    grep -q '^GLASSWELL_CSRF_KEY=.\{32,\}' /etc/glasswell/app.env
assert "a state-changing call with no csrf token is refused" 403 \
    "$(api_curl -s -o /dev/null -w '%{http_code}' --max-time 10 -X DELETE "$API/v1/session")"
assert_true "the cloudflare range list is present" "missing $CF_RANGES" test -s "$CF_RANGES"
if [[ -s $CF_RANGES ]]; then
    range_age=$(( ( $(date +%s) - $(stat -c %Y "$CF_RANGES") ) / 86400 ))
    assert_true "the cloudflare range list is fresh ($range_age d)" "older than 30 days" \
        test "$range_age" -lt 30
fi
# The freshness check above cannot fail on a deploy: install.sh rewrites the file minutes
# earlier, so it measures the deploy's own mtime. What it was standing in for is the refresher
# actually being armed, which nothing enabled and nothing asserted.
assert "glasswell-cf-ranges.timer enabled" enabled \
    "$(systemctl is-enabled glasswell-cf-ranges.timer 2>/dev/null)"
assert "glasswell-cf-ranges.timer active" active \
    "$(systemctl is-active glasswell-cf-ranges.timer 2>/dev/null)"

printf 'tunnel\n'
public_mode="$(sed -n 's/^GLASSWELL_PUBLIC=//p' /etc/glasswell/app.env)"

# Locally observable, so asserted whether or not the instance is public. These are the
# assertions that prove the exposure is safe, and a gate that can only run *after* the
# exposure proves nothing about the decision to make it.
assert_tunnel_listener_bind
assert_true "martin is loopback-only" "martin has a non-local listener" \
    listening_on '127.0.0.1:3000'
assert_false "the tracked ingress names no tile server" "127.0.0.1:3000 is published" \
    grep -q '3000' "$INFRA_DIR/cloudflared/config.yml"
if [[ -f $CLOUDFLARED_DIR/config.yml ]]; then
    assert_true "cloudflared config equals the tree" "drifted at $CLOUDFLARED_DIR/config.yml" \
        command diff -q \
            <(command sed "s|<tunnel-uuid>|$(command cat "$CLOUDFLARED_DIR/tunnel-id")|g" \
                "$INFRA_DIR/cloudflared/config.yml") \
            "$CLOUDFLARED_DIR/config.yml"
    assert_false "the installed ingress names no tile server" "127.0.0.1:3000 is published" \
        grep -q '3000' "$CLOUDFLARED_DIR/config.yml"
fi

printf 'scheduled work\n'
if systemctl list-unit-files glasswell-scheduler.timer >/dev/null 2>&1; then
    assert "glasswell-scheduler.timer enabled" enabled \
        "$(systemctl is-enabled glasswell-scheduler.timer)"
    assert "glasswell-scheduler.timer active" active \
        "$(systemctl is-active glasswell-scheduler.timer)"
    scheduler_ran="$(last_run_state "$SCHEDULER_UNIT")"
    if [[ $scheduler_ran == ran ]]; then
        assert "glasswell-scheduler.service last result" success \
            "$(systemctl show "$SCHEDULER_UNIT" -p Result --value)"
    else
        ok "glasswell-scheduler.service has not ticked yet (timer just armed)"
    fi

    # The units loop above already pins the file byte-for-byte against the tree. What that
    # cannot prove is that the running manager loaded it, so these read the applied values:
    # a unit placed and never daemon-reloaded is a sandbox that is written and not in force.
    assert "the scheduler unit runs as root" root \
        "$(systemctl show "$SCHEDULER_UNIT" -p User --value)"
    assert "the scheduler drops every capability" "" \
        "$(systemctl show "$SCHEDULER_UNIT" -p CapabilityBoundingSet --value)"
    assert "the scheduler cannot gain privileges" yes \
        "$(systemctl show "$SCHEDULER_UNIT" -p NoNewPrivileges --value)"
    assert "the scheduler's filesystem is read-only" strict \
        "$(systemctl show "$SCHEDULER_UNIT" -p ProtectSystem --value)"
    assert_false "the scheduler runs under a system-call filter" "no filter is applied" \
        test -z "$(systemctl show "$SCHEDULER_UNIT" -p SystemCallFilter --value)"

    env_mode="$(stat -c '%U:%G %a' "$SCHEDULER_ENV" 2>/dev/null)"
    assert "scheduler.env ownership and mode" 'root:root 600' "$env_mode"
    assert_false "scheduler.env carries no password" "a password reached $SCHEDULER_ENV" \
        grep -qi 'password' "$SCHEDULER_ENV"

    # Proof 3, the permanent half: no row may launch a job an installed timer already drives.
    # The timer-owned set is derived by the scheduler itself, so a unit line that names a
    # console script rather than a module is resolved through [project.scripts] rather than
    # missed — which is exactly how the neighbour index would have slipped the guard.
    # The double-run guard's own connection. Everything else here reaches PostgreSQL as
    # `postgres`, and the deploy invokes this script over a non-interactive ssh command whose
    # environment carries no DSN at all -- so the guard is handed the one install.sh writes for
    # exactly this identity, rather than left to find one that is not there.
    timer_owned="$("$VENV_PY" -m glasswell.scheduler.cli --timer-owned 2>/dev/null | wc -l)"
    # Read, never sourced. This is a systemd EnvironmentFile, which systemd parses
    # literally: the DSN carries `&user=glasswell_scheduler`, and `.` would read that as a
    # background operator and hand the guard half a DSN.
    scheduler_dsn=""
    if [[ -r $SCHEDULER_ENV ]]; then
        scheduler_dsn="$(sed -n 's/^GLASSWELL_DSN=//p' "$SCHEDULER_ENV" | head -1)"
    fi
    if [[ ${timer_owned:-0} -lt 1 ]]; then
        bad "the timer-owned entry-point set" "resolved nothing; the guard would pass vacuously"
    elif [[ -z $scheduler_dsn ]]; then
        bad "the scheduler's DSN file names a DSN" \
            "$SCHEDULER_ENV carries no GLASSWELL_DSN, so the guard could not run at all"
    else
        guard_output="$(GLASSWELL_DSN="$scheduler_dsn" \
            "$VENV_PY" -m glasswell.scheduler.cli --double-run-check 2>&1)"
        guard_status=$?
        # The status, never the message. A substring match could not tell "no launch row
        # resolved" from "I never reached the database", and reported a peer-auth failure --
        # the likeliest failure on a first deploy -- as a double-run hazard.
        case $guard_status in
            0) ok "no launch row names an entry point a timer already drives" ;;
            1)
                bad "no launch row names an entry point a timer already drives" \
                    "${guard_output//$'\n'/ } would double-run with an installed timer"
                ;;
            *)
                bad "the double-run guard ran at all" \
                    "exit $guard_status: ${guard_output//$'\n'/ }"
                ;;
        esac
    fi
    # The v0.78 posture, which inverts at the flag flip: every row this track seeds observes.
    launching="$("${PSQL[@]}" "select count(*) from lineage.job_schedules_as_of(current_date, current_date) s join lineage.scheduled_jobs j on j.job_id = s.job_id where s.launch_mode = 'launch' and (j.jurisdiction in ('ND','TX','NM','MT') or j.jurisdiction is null)")"
    assert "every resident and cross-jurisdiction row observes" 0 "$launching"
    scheduler_runs="$("${PSQL[@]}" "select count(*) from lineage.job_runs where launched_by = 'scheduler' and outcome in ('ran','failed','interrupted')")"
    assert "the scheduler has launched nothing" 0 "$scheduler_runs"

    # The CHECKs are in the migration; this asserts the resolved rows stay inside them, which
    # a row appended after the migration could otherwise leave.
    stray="$("${PSQL[@]}" "select count(*) from lineage.job_schedules_as_of(current_date, current_date) s join lineage.scheduled_jobs j on j.job_id = s.job_id where (j.run_as is not null and j.run_as not in ('glasswell','postgres')) or (j.kind <> 'maintenance' and j.entry_point !~ '^glasswell[.]')")"
    assert "no resolved row names an unknown uid or module" 0 "$stray"

    for mart in marts_nm_wells marts_mt_wells; do
        resolved="$("${PSQL[@]}" "select count(*) from lineage.job_schedules_as_of(current_date, current_date) where job_id = '$mart' and enabled")"
        assert "$mart resolves an enabled schedule" 1 "$resolved"
    done
    overdue="$(api_curl -sf --max-time 20 -H "X-Glasswell-Key: $owner_key" \
        "$API/v1/schedules/marts_nm_wells" \
        | "$VENV_PY" -c 'import json,sys; row = json.load(sys.stdin)["data"]; print(0 if row["cadence"]["note"] else 1)' 2>/dev/null)"
    assert "marts_nm_wells serves its cadence" 0 "${overdue:-1}"
else
    ok "glasswell-scheduler.timer is not installed on this host yet"
fi

printf 'scheduler identity\n'
assert "no role named root exists" 0 \
    "$("${PSQL[@]}" "select count(*) from pg_roles where rolname = 'root'")"
assert "glasswell_scheduler can log in and is not a superuser" 'f|t' \
    "$("${PSQL[@]}" "select rolsuper || '|' || rolcanlogin from pg_roles where rolname = 'glasswell_scheduler'")"
assert "glasswell_scheduler holds no pipeline membership" f \
    "$("${PSQL[@]}" "select pg_has_role('glasswell_scheduler', 'glasswell_pipeline', 'MEMBER')")"
# Derived, never enumerated: a list here would have ratified whatever it forgot, which is how
# two relations the due rule reads were left ungranted in the first place.
missing_grants=0
while read -r relation; do
    [[ -n $relation ]] || continue
    granted="$("${PSQL[@]}" "select has_table_privilege('glasswell_scheduler', '$relation', 'SELECT')")"
    [[ $granted == t ]] || { bad "glasswell_scheduler reads $relation" "no select privilege"; missing_grants=1; }
done < <("$VENV_PY" -m glasswell.scheduler.cli --read-relations 2>/dev/null)
[[ $missing_grants -eq 0 ]] && ok "glasswell_scheduler reads every relation the tick names"
outside="$("${PSQL[@]}" "select count(*) from information_schema.role_table_grants where grantee = 'glasswell_scheduler' and table_schema <> 'lineage'")"
assert "glasswell_scheduler holds no grant outside lineage" 0 "$outside"

# Read from PostgreSQL's own catalogue, not from the bytes on disk: a rule that is written
# and not reloaded is a rule that is not in force, and pg_hba.conf is package-managed with no
# tree counterpart to compare against. The drop-in does have one, so it keeps its byte pin.
ident_rows="$("${PSQL[@]}" "select count(*) from pg_ident_file_mappings where map_name = '$PG_IDENT_MAP' and error is null")"
assert "both ident mappings are live and parse clean" 2 "$ident_rows"
mapped_role="$("${PSQL[@]}" "select pg_username from pg_ident_file_mappings where map_name = '$PG_IDENT_MAP' and sys_name = 'root'")"
assert "OS root maps to the scheduler role" glasswell_scheduler "$mapped_role"
hba_mapped="$("${PSQL[@]}" "select count(*) from pg_hba_file_rules where type = 'local' and database = '{all}' and user_name = '{all}' and error is null and 'map=$PG_IDENT_MAP' = any(options)")"
assert "the local all/all rule names the map" 1 "$hba_mapped"
hba_errors="$("${PSQL[@]}" "select count(*) from pg_hba_file_rules where error is not null")"
assert "no pg_hba rule failed to parse" 0 "$hba_errors"
if [[ -f $PG_IDENT_DROPIN ]]; then
    assert_true "the ident drop-in equals the tree" "drifted at $PG_IDENT_DROPIN" \
        cmp -s "$INFRA_DIR/postgres/pg_ident.d/glasswell.conf" "$PG_IDENT_DROPIN"
fi
# Naming a map removes PostgreSQL's implicit self-mapping, so the three identities that
# authenticated before it are the ones a mistake here would silently lock out.
assert_true "glasswell still authenticates over the socket" "peer auth broke for glasswell" \
    runuser -u glasswell -- psql -d glasswell -tAc 'select 1'
assert_true "martin still authenticates over the socket" "peer auth broke for martin" \
    sudo -u martin psql -d glasswell -tAc 'select 1'
assert_true "root authenticates as the scheduler role through the map" "the map is not in force" \
    psql -d 'postgresql:///glasswell?host=/var/run/postgresql&user=glasswell_scheduler' -tAc 'select 1'

# The front door owns the CSP and is the more security-relevant of the two configs, yet only
# the connector was drift-checked; deploy never installs the Caddyfile, so the two diverge
# silently. A stale line stayed inert here for ten days before anyone noticed.
if [[ -f $CADDY_FILE ]]; then
    assert_true "caddy config equals the tree" "drifted at $CADDY_FILE" \
        command diff -q "$INFRA_DIR/caddy/Caddyfile" "$CADDY_FILE"
fi

if [[ ${public_mode:-0} == 1 ]]; then
    assert "cloudflared active" active "$(systemctl is-active cloudflared)"
    public_ip="$(dig +short "@$PUBLIC_RESOLVER" "$PUBLIC_HOST" A 2>/dev/null | grep -m1 -E '^[0-9.]+$')"
    if [[ -z $public_ip ]]; then
        # One named failure beats four probes reporting 000 and reading as an edge outage.
        bad "$PUBLIC_HOST resolves at $PUBLIC_RESOLVER" "no A record — edge probes cannot run"
    else
        edge=(--resolve "$PUBLIC_HOST:443:$public_ip")
        ok "$PUBLIC_HOST resolves to $public_ip at $PUBLIC_RESOLVER"
        assert "the non-/v1 tile path is 404 through the edge" 404 \
            "$(curl -s "${edge[@]}" -o /dev/null -w '%{http_code}' --max-time 15 \
                "https://$PUBLIC_HOST/tiles/nd_wells/8/54/89.pbf")"
        assert "the static owner key is refused through the public hostname" 403 \
            "$(curl -s "${edge[@]}" -o /dev/null -w '%{http_code}' --max-time 15 \
                -H "X-Glasswell-Key: $owner_key" "https://$PUBLIC_HOST/v1/health")"
        assert "an anonymous request through the public hostname is refused" 403 \
            "$(curl -s "${edge[@]}" -o /dev/null -w '%{http_code}' --max-time 15 \
                "https://$PUBLIC_HOST/v1/wells?limit=1")"
        assert_true "hsts is emitted through the edge" "no Strict-Transport-Security" \
            grep -qi '^strict-transport-security:' \
                <<<"$(curl -s "${edge[@]}" -D - -o /dev/null --max-time 15 \
                    "https://$PUBLIC_HOST/" | tr -d '\r')"
    fi
else
    # Skipping keeps the count honest: every pre-cutover deploy would otherwise go red on
    # three DNS-dependent probes for a hostname that deliberately does not resolve yet.
    ok "GLASSWELL_PUBLIC is 0 — the tunnel section is intentionally skipped"
fi

printf '\n%d passed, %d failed\n' "$passed" "$failed"
[[ $failed -eq 0 ]]
