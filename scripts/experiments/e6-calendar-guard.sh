#!/usr/bin/env bash
# E-6 — HORIZON_CALENDAR_GUARD_MONTHS. Decision rule: the 95th percentile of
# calendar-months-to-12-producing-months, rounded up, floored at 14 and capped at 24.
#
# The primary query needs a well to reach a 12th producing month, so it returns nothing until
# the E-0 backfill lands. The proxy below measures the producing-month rate over the loaded
# window and scales it to 12, which bounds the ordinary case but cannot see the multi-year
# shut-in the guard exists to catch. Both are printed; only the first one sets the constant.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/experiments/lib.sh
. "$SCRIPT_DIR/lib.sh"

gw_header 'E-6 calendar guard (v0.6 4A.4, SB-02 §2.2)'

rows="$(mktemp)"
trap 'rm -f "$rows"' EXIT

gw_psql <<'SQL' >"$rows"
with monthly as (
  select api10, production_month,
         bool_or((null_semantics = 'reported_zero' and days_produced > 0) or volume > 0)
             as producing
    from canonical.production_monthly_latest
   where entity_type = 'well' and source_id = 'nd_mpr_xlsx'
   group by api10, production_month
), pm as (
  select api10, production_month,
         row_number() over (partition by api10 order by production_month) as k,
         min(production_month) over (partition by api10) as t_fp
    from monthly where producing
)
select 'primary', count(*),
       coalesce(round(percentile_cont(0.50) within group (order by cal)::numeric, 2)::text, 'n/a'),
       coalesce(round(percentile_cont(0.90) within group (order by cal)::numeric, 2)::text, 'n/a'),
       coalesce(round(percentile_cont(0.95) within group (order by cal)::numeric, 2)::text, 'n/a'),
       coalesce(round(percentile_cont(0.99) within group (order by cal)::numeric, 2)::text, 'n/a')
  from (select extract(year from age(production_month, t_fp)) * 12
             + extract(month from age(production_month, t_fp)) as cal
          from pm where k = 12) x;
with monthly as (
  select api10, production_month,
         bool_or((null_semantics = 'reported_zero' and days_produced > 0) or volume > 0)
             as producing
    from canonical.production_monthly_latest
   where entity_type = 'well' and source_id = 'nd_mpr_xlsx'
   group by api10, production_month
), win as (
  select min(production_month) as lo, max(production_month) as hi
    from monthly
), p as (
  select api10, production_month, producing from monthly
), agg as (
  select p.api10, count(*) as months_observed,
         count(*) filter (where p.producing) as months_producing,
         bool_or(p.producing and p.production_month = w.lo) as prod_first,
         bool_or(p.producing and p.production_month = w.hi) as prod_last
    from p, win w group by p.api10
), full_window as (
  select * from agg
   where months_observed = (select extract(year from age(hi, lo)) * 12
                                 + extract(month from age(hi, lo)) + 1 from win)
     and prod_first and prod_last
)
select 'proxy', count(*),
       round(percentile_cont(0.50) within group (order by 12.0 * months_observed / months_producing)::numeric, 2)::text,
       round(percentile_cont(0.90) within group (order by 12.0 * months_observed / months_producing)::numeric, 2)::text,
       round(percentile_cont(0.95) within group (order by 12.0 * months_observed / months_producing)::numeric, 2)::text,
       round(100.0 * count(*) filter (where months_producing < months_observed) / count(*), 2)::text
  from full_window;
SQL

printf 'basis|wells|p50|p90|p95|p99_or_gap_pct\n'
cat "$rows"
awk -F'|' '
    $1 == "primary" && $2 + 0 == 0 {
        print "VERDICT|HORIZON_CALENDAR_GUARD_MONTHS|BLOCKED no well reaches a 12th producing month; re-run after E-0";
        next
    }
    $1 == "primary" {
        v = $5 + 0; g = (v == int(v)) ? v : int(v) + 1;
        if (g < 14) g = 14; if (g > 24) g = 24;
        printf "VERDICT|HORIZON_CALENDAR_GUARD_MONTHS|MEASURED %d (p95=%s over %s wells)\n", g, $5, $2;
    }
    $1 == "proxy" {
        printf "VERDICT|intermittent_share (proxy)|%s%% of %s wells have a gap month in the loaded window\n", $6, $2;
    }' "$rows"
