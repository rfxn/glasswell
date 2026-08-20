#!/usr/bin/env bash
# E-2 — peer-group availability across the 4A.5 fallback ladder. Decision rule: TC_MIN_N = 20
# and the 36-month vintage window stand if rung-1 share >= 0.60 and control_unavailable
# <= 0.05; otherwise widen the vintage window to 48 months first and re-run.
#
# Pre-backfill this runs on a spud-date vintage proxy and on formation_group derived from the
# loaded MPR months (G-13's mapping table does not exist yet). Set GW_E2_VINTAGE_COL=t_fp
# after E-0 to switch to first-production months.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/experiments/lib.sh
. "$SCRIPT_DIR/lib.sh"

min_n="${GW_TC_MIN_N:-20}"
window="${GW_E2_WINDOW_MONTHS:-36}"
min_count="${GW_FORMATION_GROUP_MIN_COUNT:-100}"
gw_int "$min_n"
gw_int "$window"
gw_int "$min_count"

gw_header 'E-2 peer-group availability (v0.6 4A.5, SB-02 §5.2)'
printf 'tc_min_n|window_months|subjects|rung1_share|rung2_share|rung3_share|control_unavailable_share|median_rung1_peers|median_rung2_peers\n'

rows="$(mktemp)"
trap 'rm -f "$rows"' EXIT

gw_psql -v "minn=$min_n" -v "win=$window" -v "minct=$min_count" <<'SQL' >"$rows"
with pool_rows as (
  select left(regexp_replace(api_wellno, '[^0-9]', '', 'g'), 10) as api10,
         upper(btrim(pool)) as pool, count(*) as n
    from staging.nd_mpr_oil
   where btrim(coalesce(pool, '')) <> ''
   group by 1, 2
), modal as (
  select distinct on (api10) api10, pool from pool_rows order by api10, n desc, pool
), pool_size as (
  select pool, count(*) as wells from modal group by 1
), grp as (
  select m.api10,
         case when m.pool = 'CONFIDENTIAL' then '__confidential__'
              when s.wells >= :minct then m.pool
              else '__other__' end as formation_group
    from modal m join pool_size s on s.pool = m.pool
), len as (
  select api10, sum(lateral_length_ft_exact) as len_ft from marts.nd_laterals_tile group by 1
), base as (
  select g.api10, g.formation_group, w.county_code_at_permit as area, w.spud_date as vintage,
         case when l.len_ft < 8000 then 'a' when l.len_ft < 10000 then 'b'
              when l.len_ft < 10500 then 'c' else 'd' end as bucket
    from grp g
    join canonical.wells_latest w on w.api10 = g.api10
    join len l on l.api10 = g.api10
   where w.spud_date is not null
), peers as (
  select api10,
         count(*) over (partition by formation_group, area, bucket order by vintage
                        range between (:'win' || ' months')::interval preceding
                                  and current row) - 1 as r1,
         count(*) over (partition by formation_group, area order by vintage
                        range between (:'win' || ' months')::interval preceding
                                  and current row) - 1 as r2,
         count(*) over (partition by formation_group order by vintage
                        range between (:'win' || ' months')::interval preceding
                                  and current row) - 1 as r3
    from base
), ladder as (
  select *, case when r1 >= :minn then 1 when r2 >= :minn then 2
                 when r3 >= :minn then 3 else 4 end as rung
    from peers
)
select :minn, :win, count(*),
       round(avg((rung = 1)::int)::numeric, 4),
       round(avg((rung = 2)::int)::numeric, 4),
       round(avg((rung = 3)::int)::numeric, 4),
       round(avg((rung = 4)::int)::numeric, 4),
       percentile_cont(0.5) within group (order by r1),
       percentile_cont(0.5) within group (order by r2)
  from ladder;
SQL

cat "$rows"
awk -F'|' '{
    pass = ($4 + 0 >= 0.60 && $7 + 0 <= 0.05) ? "PASS" : "FAIL";
    printf "VERDICT|TC_MIN_N=%s VINTAGE_WINDOW_MONTHS=%s|%s rung1=%s control_unavailable=%s\n",
           $1, $2, pass, $4, $7;
}' "$rows"
