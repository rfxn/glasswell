#!/usr/bin/env bash
# Shared plumbing for the pre-P3 gate experiments (work-output/pre-p3-gate.md §2).
# Read-only by construction: every experiment sends SELECTs on stdin and nothing else.

gw_die() {
    printf 'error: %s\n' "$1" >&2
    exit 2
}

gw_int() {
    case "$1" in
        '' | *[!0-9]*) gw_die "expected an integer, got '$1'" ;;
    esac
}

gw_db_env() {
    printf '%s' "${GLASSWELL_DB_ENV:-/etc/glasswell/db.env}"
}

gw_dsn() {
    if [ -n "${GLASSWELL_DSN:-}" ]; then
        printf '%s' "$GLASSWELL_DSN"
        return
    fi
    local env_file
    env_file="$(gw_db_env)"
    [ -r "$env_file" ] || gw_die "no GLASSWELL_DSN and $env_file is unreadable; set GLASSWELL_SSH to run remotely"
    sed -n 's/^DATABASE_URL=//p' "$env_file"
}

# SQL arrives on stdin; any -v assignments are passed through as arguments.
# shellcheck disable=SC2120  # most callers pass no -v assignments, which is not a defect
gw_psql() {
    if [ -n "${GLASSWELL_SSH:-}" ]; then
        local passthrough
        passthrough="$(printf '%q ' "$@")"
        # shellcheck disable=SC2029  # the db.env path resolves here on purpose; the DSN never leaves the host
        ssh "$GLASSWELL_SSH" \
            "psql \"\$(sed -n 's/^DATABASE_URL=//p' $(gw_db_env))\" -v ON_ERROR_STOP=1 -At -F'|' $passthrough -f -"
    else
        psql "$(gw_dsn)" -v ON_ERROR_STOP=1 -At -F'|' "$@" -f -
    fi
}

gw_header() {
    printf '# %s\n# run: %s  target: %s\n' "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        "${GLASSWELL_SSH:-local}"
}

# A verdict line is the mechanical half of a decision rule: re-running after the E-0 backfill
# re-decides the constant without a second judgment call.
gw_verdict() {
    printf 'VERDICT|%s|%s\n' "$1" "$2"
}
