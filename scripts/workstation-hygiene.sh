#!/usr/bin/env bash
# DIR-14: a workstation runs the editor and fast test iteration. Anything of glasswell's that
# is persistent, scheduled, or serving belongs on VM 111 (app, data, timers) or anvil (CI-scale
# docker). This flags what has accumulated here instead. Read-only: it reclaims nothing.
set -uo pipefail

CONTAINER_MAX_HOURS="${CONTAINER_MAX_HOURS:-2}"
SCRATCH_WARN_MB="${SCRATCH_WARN_MB:-50}"
TEST_LABEL="${TEST_LABEL:-glasswell.test}"

passed=0
failed=0
warned=0

ok() { printf '  ok   %s\n' "$1"; passed=$((passed + 1)); }
bad() { printf '  FAIL %s — %s\n' "$1" "$2"; failed=$((failed + 1)); }
warn() { printf '  warn %s — %s\n' "$1" "$2"; warned=$((warned + 1)); }

assert_empty() {
    local label="$1" detail="$2" found="$3"
    if [[ -z $found ]]; then
        ok "$label"
    else
        bad "$label" "$detail: $(printf '%s' "$found" | tr '\n' ' ')"
    fi
}

printf 'scheduled and persistent units\n'
units=$(systemctl list-unit-files --no-pager --no-legend 2>/dev/null \
    | awk '{print $1}' | grep -i glasswell)
assert_empty "no glasswell systemd unit is installed" "belongs on VM 111" "$units"

user_units=$(systemctl --user list-unit-files --no-pager --no-legend 2>/dev/null \
    | awk '{print $1}' | grep -i glasswell)
assert_empty "no glasswell user unit is installed" "belongs on VM 111" "$user_units"

cron_hits=$( { crontab -l 2>/dev/null; cat /etc/cron.d/* 2>/dev/null; } \
    | grep -iv '^[[:space:]]*#' | grep -i 'glasswell' )  # no crontab is not an error
assert_empty "no glasswell cron entry" "belongs on VM 111" "$cron_hits"

printf 'serving\n'
# A dev server on loopback is iteration; anything of ours bound to a routable address is not.
lan_listeners=$(ss -ltnp 2>/dev/null \
    | grep -viE '^State|127\.0\.0\.1|\[::1\]' \
    | grep -iE 'glasswell|gw-|uvicorn|martin|vite' \
    | awk '{print $4}')
assert_empty "nothing glasswell is bound to a routable address" "belongs on VM 111" \
    "$lan_listeners"

stale_servers=$(pgrep -af '/tmp/gw-[^ ]*serve|/tmp/gw-[^ ]*http' 2>/dev/null)  # no match is the good case
assert_empty "no scratch dev server is still running" "left by an agent" "$stale_servers"

printf 'docker residue\n'
if ! docker info >/dev/null 2>&1; then  # a workstation without docker has nothing to sweep
    warn "docker state" "no reachable daemon, skipped"
else
    orphan_volumes=$(docker volume ls -q --filter "label=$TEST_LABEL" --filter dangling=true 2>&1)
    assert_empty "no labelled test volume outlived its session" \
        "run: make prune-test-volumes" "$orphan_volumes"

    stale_containers=$(docker ps --filter "label=$TEST_LABEL" \
        --format '{{.Names}} {{.RunningFor}}' 2>/dev/null \
        | grep -E "([2-9]|[0-9]{2,}) hours|days|weeks|months")
    assert_empty "no test container outlived a suite run" \
        "older than ${CONTAINER_MAX_HOURS}h, docker rm -f it" "$stale_containers"

    # buildx keeps its builder state in a volume nothing links to; it is not residue.
    dangling=$(docker volume ls -q --filter dangling=true 2>/dev/null | grep -cv '^buildx_')
    if [[ $dangling -gt 0 ]]; then
        warn "$dangling unlabelled dangling volume(s)" \
            "pre-label residue the sweep cannot see; docker volume prune"
    else
        ok "no unlabelled dangling volumes"
    fi
fi

printf 'scratch\n'
scratch=$(find /tmp -maxdepth 1 -name 'gw-*' -o -maxdepth 1 -name 'glasswell-*' 2>/dev/null)
if [[ -n $scratch ]]; then
    total_kb=$(printf '%s\n' "$scratch" | xargs -r du -sk 2>/dev/null | awk '{s+=$1} END {print s+0}')
    if [[ $((total_kb / 1024)) -gt $SCRATCH_WARN_MB ]]; then
        warn "$((total_kb / 1024)) MB of /tmp/gw-* scratch" \
            "fine while a task runs, residue after it; /tmp is tmpfs, so this is RAM"
    else
        ok "/tmp scratch under ${SCRATCH_WARN_MB} MB"
    fi
else
    ok "no /tmp scratch"
fi

# A regulator download outside the raw zone has no fetch manifest, so nothing derived from it
# is reproducible. Re-fetch through the ingest path on VM 111 instead of promoting these.
unsealed=$(find /tmp /root -maxdepth 1 \( -name 'OGD_*.zip' -o -name '*_MPR_*.xlsx' \) 2>/dev/null)
assert_empty "no unsealed regulator download" "the raw zone on VM 111 is the system of record" \
    "$unsealed"

# scripts/basemap-build.sh writes to ./basemap by default, and the Permian extract is 336 MB.
# Persistent locations only: a /tmp archive cannot survive the machine, which is DIR-14's test.
extracts=$(find . "$HOME" -maxdepth 6 -name '*.pmtiles' -size +1M 2>/dev/null)
assert_empty "no basemap extract kept here" "build heavy extracts on VM 111" "$extracts"

printf '\n%d ok, %d warn, %d FAIL\n' "$passed" "$warned" "$failed"
[[ $failed -eq 0 ]]
