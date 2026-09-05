#!/usr/bin/env bash
# Run a long host job as a chain of transient units and publish where it got to, so the job
# outlives the shell that started it and is read from a file rather than from an ssh exit.
# ARCHITECTURE.md § Operations states the rule; `--help` states the grammar.
set -uo pipefail

RUNS_DIR="${GLASSWELL_RUNS_DIR:-/var/lib/glasswell/runs}"
LOG_DIR="${GLASSWELL_LOG_DIR:-/var/log/glasswell}"
CODE_ENV_FILE="${GLASSWELL_CODE_ENV_FILE:-/etc/glasswell/code-version.env}"
SOCKET_DSN="${GLASSWELL_DSN:-postgresql:///glasswell?host=/var/run/postgresql}"
RAW_ROOT="${GLASSWELL_RAW_ROOT:-/data/raw}"
PGDATA_DIR="${GLASSWELL_PGDATA:-/var/lib/postgresql}"
WAIT_INTERVAL="${GLASSWELL_WAIT_INTERVAL:-30}"

DEFAULT_MEMORY=6G
DEFAULT_TIMEOUT=3600
NAME_PATTERN='^[A-Za-z0-9][A-Za-z0-9._-]*$'
INTEGER_PATTERN='^[0-9]+$'

usage() {
    cat <<'USAGE'
usage: host-runner.sh --job <name> [options] -- <step> [step-options] <command...> [-- <step> ...]
       host-runner.sh --job <name> --steps-file <path> [options]
       host-runner.sh --status <job>
       host-runner.sh --record --job <name> --step <name> --step-index <n> \
                      --steps-total <n> --result <word> [--exit <n>] [--unit <name>] [--summary <text>]

One transient unit per step, `systemd-run --wait` inside this script and nowhere else. The log
is $GLASSWELL_LOG_DIR/<job>.log and the status is $GLASSWELL_RUNS_DIR/<job>.json, rewritten
whole after every transition. Poll the status file; do not read an ssh exit as the answer.

options:
  --job <name>          names the log, the status file and the units      (required)
  --steps-file <path>   one step per line, `#` comments; a line is not shell-quoted
  --detach              hand the chain to a transient unit and return the poll command
  --force               run a job whose status file says it already ran, from step 1
  --resume              continue a stopped job: same status file, same log, same job name,
                        the earlier steps kept and the new ones numbered after them
  --after-job <job>     wait for another job's status file to finish, and refuse to start
                        behind one that stopped
  --stop-on-fail        stop at the first failing step (the default)
  --keep-going          run every step even after one fails; the job still reports `stopped`
  --user/--group <n>    the unit's User=/Group= (default glasswell)
  --memory <max>        default MemoryMax per step (default 6G)
  --timeout <seconds>   default RuntimeMaxSec and TimeoutStartSec per step (default 3600)
  --setenv <K=V>        an extra environment variable for every step, repeatable
  --status <job>        print the job's status JSON and exit
  --record              write one transition into a job's status file (for scripted chains)

step options, before the command: --unit, --memory, --timeout, --user, --group, --setenv.

exit: 0 the chain completed, the failing step's status when it did not, 2 a usage refusal,
      3 a refusal to re-run a job that already has a status file, or to resume one that
        did not stop.
USAGE
}

fail_usage() {
    printf 'host-runner.sh: %s\n' "$1" >&2
    printf 'run with --help for the grammar\n' >&2
    exit 2
}

now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# JSON has no escape-free string: a journal line carries quotes, backslashes and tabs, and one
# unescaped byte would make the status file unreadable to the poller it exists for.
json_string() {
    local raw=$1
    raw=${raw//\\/\\\\}
    raw=${raw//\"/\\\"}
    raw=${raw//$'\t'/\\t}
    raw=${raw//$'\r'/\\r}
    raw=${raw//$'\n'/\\n}
    printf '"%s"' "$raw"
}

json_or_null() {
    if [[ -z $1 ]]; then printf 'null'; else json_string "$1"; fi
}

job=""
steps_file=""
status_query=""
mode=chain
force=0
resume=0
detach=0
after_job=""
stop_on_fail=1
default_user=glasswell
default_group=glasswell
default_memory=$DEFAULT_MEMORY
default_timeout=$DEFAULT_TIMEOUT
global_setenv=()
record_name=""
record_index=""
record_total=""
record_result=""
record_exit=""
record_unit="none"
record_summary=""
original_argv=("$@")

while [[ $# -gt 0 ]]; do
    case "$1" in
        --job|--steps-file|--status|--step|--step-index|--steps-total|--result|--exit|--unit|--summary|--user|--group|--memory|--timeout|--setenv|--after-job)
            [[ $# -ge 2 ]] || fail_usage "$1 needs a value"
            ;;
    esac
    case "$1" in
        --job) job=$2; shift 2 ;;
        --steps-file) steps_file=$2; shift 2 ;;
        --status) status_query=$2; shift 2 ;;
        --record) mode=record; shift ;;
        --step) record_name=$2; shift 2 ;;
        --step-index) record_index=$2; shift 2 ;;
        --steps-total) record_total=$2; shift 2 ;;
        --result) record_result=$2; shift 2 ;;
        --exit) record_exit=$2; shift 2 ;;
        --unit) record_unit=$2; shift 2 ;;
        --summary) record_summary=$2; shift 2 ;;
        --detach) detach=1; shift ;;
        --force) force=1; shift ;;
        --resume) resume=1; shift ;;
        --after-job) after_job=$2; shift 2 ;;
        --stop-on-fail) stop_on_fail=1; shift ;;
        --keep-going) stop_on_fail=0; shift ;;
        --user) default_user=$2; shift 2 ;;
        --group) default_group=$2; shift 2 ;;
        --memory) default_memory=$2; shift 2 ;;
        --timeout) default_timeout=$2; shift 2 ;;
        --setenv) global_setenv+=("$2"); shift 2 ;;
        -h|--help) usage; exit 0 ;;
        --) shift; break ;;
        *) fail_usage "unknown argument: $1" ;;
    esac
done

if [[ -n $status_query ]]; then
    [[ $status_query =~ $NAME_PATTERN ]] || fail_usage "job name '$status_query' is not a name"
    status_path="$RUNS_DIR/$status_query.json"
    if [[ ! -f $status_path ]]; then
        printf 'host-runner.sh: no status for job %s at %s\n' "$status_query" "$status_path" >&2
        exit 1
    fi
    command cat "$status_path"
    exit 0
fi

[[ -n $job ]] || fail_usage "--job is required"
[[ $job =~ $NAME_PATTERN ]] || fail_usage "job name '$job' is not a name"

status_file="$RUNS_DIR/$job.json"
steps_record="$RUNS_DIR/$job.steps"
stamps_file="$RUNS_DIR/$job.stamps"
log_file="$LOG_DIR/$job.log"

ensure_directory() {
    [[ -d $1 ]] && return 0
    command install -d -m "$2" "$1" || {
        printf 'host-runner.sh: cannot create %s\n' "$1" >&2
        exit 1
    }
}

stamp() { printf '%s %s\n' "$(now)" "$1" >> "$stamps_file"; }

record_step() {
    local index=$1 name=$2 unit=$3 started_at=$4 ended_at=$5 exit_code=$6
    local systemd_result=$7 memory_peak=$8 summary=$9
    printf '{"index":%s,"step":%s,"unit":%s,"started":%s,"ended":%s,"exit":%s,' \
        "$index" "$(json_string "$name")" "$(json_string "$unit")" \
        "$(json_string "$started_at")" "$(json_or_null "$ended_at")" \
        "${exit_code:-null}" >> "$steps_record"
    printf '"systemd_result":%s,"memory_peak":%s,"summary":%s}\n' \
        "$(json_or_null "$systemd_result")" "$(json_or_null "$memory_peak")" \
        "$(json_string "$summary")" >> "$steps_record"
}

# The last record per step index wins, so a step that started and then ended is one entry rather
# than two, and a killed runner leaves the file readable exactly as far as it got.
collect_records() {
    local line index
    records=()
    highest_index=0
    [[ -f $steps_record ]] || return 0
    while IFS= read -r line; do
        index=${line#*\"index\":}
        index=${index%%,*}
        [[ $index =~ $INTEGER_PATTERN ]] || continue
        records[index]=$line
        if (( index > highest_index )); then highest_index=$index; fi
    done < "$steps_record"
}

write_status() {
    local result=$1 step=$2 index=$3 unit=$4 exit_json=$5 finished_json=$6
    local line position first=1
    collect_records
    {
        printf '{"job":%s,"started":%s,"updated":%s,' \
            "$(json_string "$job")" "$(json_string "$started")" "$(json_string "$(now)")"
        printf '"step":%s,"step_index":%s,"steps_total":%s,"unit":%s,' \
            "$(json_string "$step")" "$index" "$steps_total" "$(json_string "$unit")"
        printf '"exit":%s,"result":%s,"finished":%s,"log":%s,"steps":[' \
            "$exit_json" "$(json_string "$result")" "$finished_json" "$(json_string "$log_file")"
        for (( position = 1; position <= highest_index; position++ )); do
            [[ -n ${records[position]:-} ]] || continue
            if (( first == 0 )); then printf ','; fi
            first=0
            printf '%s' "${records[position]}"
        done
        printf '],"stamps":['
        first=1
        if [[ -f $stamps_file ]]; then
            while IFS= read -r line; do
                if (( first == 0 )); then printf ','; fi
                first=0
                json_string "$line"
            done < "$stamps_file"
        fi
        printf ']}\n'
    } > "$status_file.tmp" && command mv "$status_file.tmp" "$status_file"
}

# Anchored on the document this script writes: the top-level keys are the first two, and a
# quote inside a step summary is escaped, so no summary can answer for the job.
status_field() {
    case "$2" in
        started) sed -n 's/^{"job":"[^"]*","started":"\([^"]*\)".*/\1/p' "$1" ;;
        result) sed -n 's/.*,"result":"\([^"]*\)".*/\1/p' "$1" ;;
        finished) sed -n 's/.*,"finished":"\([^"]*\)".*/\1/p' "$1" ;;
        step) sed -n 's/.*,"step":"\([^"]*\)".*/\1/p' "$1" ;;
        updated) sed -n 's/.*,"updated":"\([^"]*\)".*/\1/p' "$1" ;;
    esac
}

ensure_directory "$RUNS_DIR" 0750
ensure_directory "$LOG_DIR" 0755

if [[ $mode == record ]]; then
    [[ -n $record_name ]] || fail_usage "--record needs --step"
    [[ $record_index =~ $INTEGER_PATTERN ]] || fail_usage "--step-index must be a number"
    [[ $record_total =~ $INTEGER_PATTERN ]] || fail_usage "--steps-total must be a number"
    case "$record_result" in
        starting|waiting|running|step-ok|stopped|complete) ;;
        *) fail_usage "--result is one of starting, waiting, running, step-ok, stopped, complete" ;;
    esac
    [[ -z $record_exit || $record_exit =~ $INTEGER_PATTERN ]] || fail_usage "--exit must be a number"

    steps_total=$record_total
    started=""
    [[ -f $status_file ]] && started=$(status_field "$status_file" started)
    [[ -n $started ]] || started=$(now)

    last_record() {
        [[ -f $steps_record ]] || return 0
        grep -F "{\"index\":$1," "$steps_record" | tail -n 1
    }

    record_value() {
        local rest=${1#*\""$2"\":\"}
        printf '%s' "${rest%%\"*}"
    }

    # The highest step whose last record has no end. A scripted chain closes it when the next
    # step opens, because a linear chain that refuses on failure has no other reading of
    # "the next step started".
    open_record_index() {
        local position open=""
        collect_records
        for (( position = 1; position <= highest_index; position++ )); do
            case "${records[position]:-}" in *'"ended":null'*) open=$position ;; esac
        done
        printf '%s' "$open"
    }

    close_record() {
        local index=$1 exit_code=$2 systemd_result=$3 summary=$4 line
        line=$(last_record "$index")
        [[ -n $line ]] || return 0
        record_step "$index" "$(record_value "$line" step)" "$(record_value "$line" unit)" \
            "$(record_value "$line" started)" "$(now)" "$exit_code" "$systemd_result" "" "$summary"
    }

    open_index=$(open_record_index)
    case "$record_result" in
        starting|waiting)
            write_status "$record_result" "$record_name" "$record_index" "$record_unit" null null
            ;;
        running)
            if [[ -n $open_index && $open_index != "$record_index" ]]; then
                close_record "$open_index" 0 success ""
            fi
            record_step "$record_index" "$record_name" "$record_unit" "$(now)" "" "" "" "" ""
            stamp "$record_name start"
            write_status running "$record_name" "$record_index" "$record_unit" null null
            ;;
        step-ok)
            close_record "$record_index" 0 success "$record_summary"
            stamp "$record_name end rc=0"
            write_status step-ok "$record_name" "$record_index" "$record_unit" 0 null
            ;;
        stopped)
            close_record "$record_index" "${record_exit:-1}" exit-code "$record_summary"
            stamp "$record_name end rc=${record_exit:-1}"
            write_status stopped "$record_name" "$record_index" "$record_unit" \
                "${record_exit:-1}" "$(json_string "$(now)")"
            ;;
        complete)
            if [[ -n $open_index ]]; then close_record "$open_index" 0 success "$record_summary"; fi
            stamp "$record_name complete"
            write_status complete "$record_name" "$record_index" "$record_unit" 0 \
                "$(json_string "$(now)")"
            ;;
    esac
    exit 0
fi

if [[ -n $after_job ]]; then
    [[ $after_job =~ $NAME_PATTERN ]] || fail_usage "job name '$after_job' is not a name"
    [[ -f "$RUNS_DIR/$after_job.json" ]] \
        || fail_usage "no status for job $after_job — a job that never ran cannot be followed"
fi

index_offset=0
started=""
if [[ -f $status_file ]]; then
    prior_result=$(status_field "$status_file" result)
    prior_finished=$(status_field "$status_file" finished)
    if (( resume )); then
        if [[ $prior_result != stopped ]]; then
            printf 'host-runner.sh: job %s is %s, not stopped — --resume continues a job that stopped\n' \
                "$job" "$prior_result" >&2
            exit 3
        fi
        # The steps already recorded stay and the new ones are numbered after them: the
        # history the status file carries is the job's, not this run's.
        collect_records
        index_offset=$highest_index
        started=$(status_field "$status_file" started)
    elif (( force == 0 )); then
        if [[ -n $prior_finished ]]; then
            printf 'host-runner.sh: job %s already finished (%s) at %s — pass --force to run it again\n' \
                "$job" "$prior_result" "$prior_finished" >&2
        else
            printf 'host-runner.sh: job %s has a run in progress (step %s, updated %s) — pass --force to run it again\n' \
                "$job" "$(status_field "$status_file" step)" "$(status_field "$status_file" updated)" >&2
        fi
        exit 3
    fi
elif (( resume )); then
    printf 'host-runner.sh: no status for job %s at %s — there is nothing to resume\n' \
        "$job" "$status_file" >&2
    exit 3
fi
[[ -n $started ]] || started=$(now)

step_names=()
step_units=()
step_memory=()
step_timeout=()
step_user=()
step_group=()
step_setenv_offset=()
step_setenv_count=()
step_command_offset=()
step_command_count=()
setenv_flat=()
command_flat=()
steps_total=$index_offset

parse_steps() {
    local name unit memory timeout user group
    local -a step_env command_argv
    while [[ $# -gt 0 ]]; do
        name=$1
        shift
        [[ $name =~ $NAME_PATTERN ]] || fail_usage "step name '$name' is not a name"
        unit=""
        memory=$default_memory
        timeout=$default_timeout
        user=$default_user
        group=$default_group
        step_env=(${global_setenv[@]+"${global_setenv[@]}"})
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --unit|--memory|--timeout|--user|--group|--setenv)
                    [[ $# -ge 2 ]] || fail_usage "$1 needs a value"
                    ;;
            esac
            case "$1" in
                --unit) unit=$2; shift 2 ;;
                --memory) memory=$2; shift 2 ;;
                --timeout) timeout=$2; shift 2 ;;
                --user) user=$2; shift 2 ;;
                --group) group=$2; shift 2 ;;
                --setenv) step_env+=("$2"); shift 2 ;;
                *) break ;;
            esac
        done
        command_argv=()
        while [[ $# -gt 0 && $1 != -- ]]; do
            command_argv+=("$1")
            shift
        done
        if [[ $# -gt 0 ]]; then shift; fi
        (( ${#command_argv[@]} > 0 )) || fail_usage "step '$name' has no command"

        steps_total=$(( steps_total + 1 ))
        step_names[steps_total]=$name
        step_units[steps_total]=${unit:-$job-$steps_total-$name}
        step_memory[steps_total]=$memory
        step_timeout[steps_total]=$timeout
        step_user[steps_total]=$user
        step_group[steps_total]=$group
        step_setenv_offset[steps_total]=${#setenv_flat[@]}
        step_setenv_count[steps_total]=${#step_env[@]}
        setenv_flat+=(${step_env[@]+"${step_env[@]}"})
        step_command_offset[steps_total]=${#command_flat[@]}
        step_command_count[steps_total]=${#command_argv[@]}
        command_flat+=("${command_argv[@]}")
    done
}

if [[ -n $steps_file ]]; then
    [[ -f $steps_file ]] || fail_usage "no steps file at $steps_file"
    file_tokens=()
    while IFS= read -r file_line || [[ -n $file_line ]]; do
        [[ $file_line =~ ^[[:space:]]*(#|$) ]] && continue
        read -r -a file_words <<< "$file_line"
        file_tokens+=("${file_words[@]}" --)
    done < "$steps_file"
    (( ${#file_tokens[@]} > 0 )) || fail_usage "$steps_file names no step"
    parse_steps "${file_tokens[@]}"
else
    (( $# > 0 )) || fail_usage "no steps — the chain is everything after --"
    parse_steps "$@"
fi

(( steps_total > index_offset )) || fail_usage "no steps"

self_path="$(cd -- "$(dirname -- "$0")" && pwd)/$(basename -- "$0")" || {
    printf 'host-runner.sh: cannot resolve my own path\n' >&2
    exit 1
}

if (( detach )); then
    # A resume reuses the job name, and a failed unit still loaded under it would refuse.
    systemctl reset-failed "$job-runner" >/dev/null 2>&1  # not-loaded is the goal, not an error
    detach_argv=()
    for argument in ${original_argv[@]+"${original_argv[@]}"}; do
        [[ $argument == --detach ]] && continue
        detach_argv+=("$argument")
    done
    systemd-run --unit="$job-runner" --collect --description="glasswell job $job" \
        --property=TimeoutStartSec=infinity "$self_path" ${detach_argv[@]+"${detach_argv[@]}"}
    launch_status=$?
    if (( launch_status != 0 )); then
        printf 'host-runner.sh: could not launch %s-runner\n' "$job" >&2
        exit "$launch_status"
    fi
    # The next line of every runbook polls this file, so do not hand back the command to poll
    # it until the job it launched has written one.
    detach_ready=0
    for (( attempt = 0; attempt < 25; attempt++ )); do
        if [[ -f $status_file ]]; then detach_ready=1; break; fi
        sleep 0.2
    done
    printf 'job %s is running as %s-runner; %s steps; log %s\n' \
        "$job" "$job" "$steps_total" "$log_file"
    if (( detach_ready == 0 )); then
        printf 'host-runner.sh: nothing has been written to %s yet — check %s-runner\n' \
            "$status_file" "$job" >&2
    fi
    printf 'poll: %s --status %s\n' "$self_path" "$job"
    exit 0
fi

if (( resume == 0 )); then
    : > "$steps_record"
    : > "$stamps_file"
fi

printf 'job %s: %s steps; log %s\n' "$job" "$steps_total" "$log_file" >&2
printf 'poll: %s --status %s\n' "$self_path" "$job" >&2

exec >>"$log_file" 2>&1

# What the host had left when the step began; both are absent under a test harness.
host_pressure() {
    local memory_free="" pgdata_free=""
    if command -v free >/dev/null 2>&1; then memory_free=$(free -m | awk '/^Mem:/{print $7}'); fi
    if [[ -d $PGDATA_DIR ]]; then
        pgdata_free=$(df -h "$PGDATA_DIR" | tail -1 | awk '{print $4}')
    fi
    printf 'mem_avail=%sMiB pgdata_free=%s' "${memory_free:-unknown}" "${pgdata_free:-unknown}"
}

# The step's own last machine-readable line, whole. Truncating it is what made the first host
# instance's figures unparseable, so nothing here cuts, heads or tails a line.
step_summary() {
    local text line last_json="" last_line=""
    text=$(printf '%s\n' "$1" | LC_ALL=C tr -d '\000-\010\013\014\016-\037\177')
    while IFS= read -r line; do
        [[ -n $line ]] || continue
        last_line=$line
        case "$line" in \{*) last_json=$line ;; esac
    done <<< "$text"
    if [[ -n $last_json ]]; then printf '%s' "$last_json"; else printf '%s' "$last_line"; fi
}

# The job this one follows is read from its status file, never from a unit's Result: a
# transient unit that has been collected answers `success` however it ended.
wait_for_job() {
    local awaited="$RUNS_DIR/$after_job.json" finished_at result_word
    printf '== waiting for job %s (%s)\n' "$after_job" "$awaited"
    while :; do
        finished_at=$(status_field "$awaited" finished)
        [[ -n $finished_at ]] && break
        write_status waiting "after $after_job" 0 "$after_job" null null
        sleep "$WAIT_INTERVAL"
    done
    result_word=$(status_field "$awaited" result)
    if [[ $result_word != complete ]]; then
        printf 'STOP: job %s is %s at %s — this job does not start behind it\n' \
            "$after_job" "$result_word" "$finished_at"
        write_status stopped "after $after_job" 0 "$after_job" 1 "$(json_string "$(now)")"
        exit 1
    fi
    printf '== job %s completed at %s\n' "$after_job" "$finished_at"
}

run_step() {
    local index=$1
    local name=${step_names[index]} unit=${step_units[index]}
    local started_at ended_at exit_status systemd_result exec_status memory_peak journal summary
    local -a command_argv properties step_env=()
    command_argv=("${command_flat[@]:${step_command_offset[index]}:${step_command_count[index]}}")
    if (( step_setenv_count[index] > 0 )); then
        step_env=("${setenv_flat[@]:${step_setenv_offset[index]}:${step_setenv_count[index]}}")
    fi
    properties=(
        "--property=User=${step_user[index]}"
        "--property=Group=${step_group[index]}"
        "--property=Environment=GLASSWELL_DSN=$SOCKET_DSN"
        "--property=Environment=GLASSWELL_RAW_ROOT=$RAW_ROOT"
        "--property=EnvironmentFile=-$CODE_ENV_FILE"
        "--property=TimeoutStartSec=${step_timeout[index]}"
        "--property=RuntimeMaxSec=${step_timeout[index]}"
        "--property=MemoryMax=${step_memory[index]}"
    )
    local setting
    for setting in ${step_env[@]+"${step_env[@]}"}; do
        properties+=("--setenv=$setting")
    done

    started_at=$(now)
    printf '== %s unit=%s start=%s %s\n' "$name" "$unit" "$started_at" "$(host_pressure)"
    stamp "$name start"
    record_step "$index" "$name" "$unit" "$started_at" "" "" "" "" ""
    write_status running "$name" "$index" "$unit" null null

    # A failed unit from an earlier run stays loaded, and its name would refuse this one.
    systemctl reset-failed "$unit" >/dev/null 2>&1  # not-loaded is the goal, not an error

    systemd-run --unit="$unit" --wait "${properties[@]}" "${command_argv[@]}"
    exit_status=$?
    ended_at=$(now)
    systemd_result=$(systemctl show "$unit" -p Result --value)
    exec_status=$(systemctl show "$unit" -p ExecMainStatus --value)
    memory_peak=$(systemctl show "$unit" -p MemoryPeak --value)
    journal=$(journalctl -u "$unit" --no-pager -o cat)
    summary=$(step_summary "$journal")

    printf -- '-- journal %s --\n%s\n-- end journal %s --\n' "$unit" "$journal" "$unit"
    printf '== %s unit=%s end=%s rc=%s Result=%s ExecMainStatus=%s MemoryPeak=%s\n' \
        "$name" "$unit" "$ended_at" "$exit_status" "$systemd_result" "$exec_status" "$memory_peak"
    stamp "$name end rc=$exit_status Result=$systemd_result ExecMainStatus=$exec_status MemoryPeak=$memory_peak"
    record_step "$index" "$name" "$unit" "$started_at" "$ended_at" "$exit_status" \
        "$systemd_result" "$memory_peak" "$summary"

    if (( exit_status != 0 )) || [[ $systemd_result != success || $exec_status != 0 ]]; then
        printf 'STOP at %s (%s): rc=%s Result=%s ExecMainStatus=%s — the unit is left loaded for inspection\n' \
            "$name" "$unit" "$exit_status" "$systemd_result" "$exec_status"
        if (( exit_status == 0 )); then exit_status=1; fi
        return "$exit_status"
    fi
    write_status step-ok "$name" "$index" "$unit" 0 null
    return 0
}

if (( resume )); then
    stamp "resumed at step $(( index_offset + 1 ))"
    printf '== job %s resumed %s at step %s of %s\n' \
        "$job" "$(now)" "$(( index_offset + 1 ))" "$steps_total"
fi
write_status starting "" "$index_offset" "" null null
if [[ -n $after_job ]]; then wait_for_job; fi
printf '== job %s start=%s steps=%s code=%s\n' "$job" "$started" "$steps_total" \
    "$(sed -n 's/^GLASSWELL_CODE_VERSION=//p' "$CODE_ENV_FILE" 2>/dev/null)"  # absent off-host, and empty is the right answer

failed_index=0
failed_exit=0
for (( step_position = index_offset + 1; step_position <= steps_total; step_position++ )); do
    run_step "$step_position"
    step_status=$?
    if (( step_status != 0 )); then
        if (( failed_index == 0 )); then
            failed_index=$step_position
            failed_exit=$step_status
        fi
        if (( stop_on_fail )); then break; fi
    fi
done

finished_at=$(now)
if (( failed_index != 0 )); then
    printf '== job %s stopped at %s rc=%s %s\n' \
        "$job" "${step_names[failed_index]}" "$failed_exit" "$finished_at"
    write_status stopped "${step_names[failed_index]}" "$failed_index" \
        "${step_units[failed_index]}" "$failed_exit" "$(json_string "$finished_at")"
    exit "$failed_exit"
fi

printf '== job %s complete %s\n' "$job" "$finished_at"
write_status complete "${step_names[steps_total]}" "$steps_total" "${step_units[steps_total]}" \
    0 "$(json_string "$finished_at")"
