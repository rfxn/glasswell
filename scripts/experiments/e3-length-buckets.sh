#!/usr/bin/env bash
# E-3 — lateral-length bucket cut points for the Mondrian taxonomy and the 4A.5 peer group.
# Decision rule: the pinned cuts {<7500, 7500-9500, 9500-11000, >11000} stand iff every
# bucket holds >= 15% of matured wells; otherwise the measured quartiles snapped to the
# nearest 500 ft replace them.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/experiments/lib.sh
. "$SCRIPT_DIR/lib.sh"

gw_header 'E-3 lateral-length buckets (SB-02 §4.4, §5.2)'

rows="$(mktemp)"
trap 'rm -f "$rows"' EXIT

# Before E-0 there is no matured-well population, so the quantiles are taken over every well
# with a promoted centreline. The restriction is a where-clause away once labels exist.
gw_psql <<'SQL' >"$rows"
with t as (
  select api10, sum(lateral_length_ft_exact) as len_ft from marts.nd_laterals_tile group by api10
)
select 'quantiles', count(*),
       round(percentile_cont(0.25) within group (order by len_ft)::numeric, 0),
       round(percentile_cont(0.50) within group (order by len_ft)::numeric, 0),
       round(percentile_cont(0.75) within group (order by len_ft)::numeric, 0),
       round(percentile_cont(0.90) within group (order by len_ft)::numeric, 0),
       round(min(len_ft)::numeric, 0), round(max(len_ft)::numeric, 0)
  from t;
with t as (
  select api10, sum(lateral_length_ft_exact) as len_ft from marts.nd_laterals_tile group by api10
)
select 'pinned_bucket',
       (case when len_ft < 7500 then 1 when len_ft < 9500 then 2
             when len_ft < 11000 then 3 else 4 end),
       count(*), round(100.0 * count(*) / sum(count(*)) over (), 2)
  from t group by 2 order by 2;
with t as (
  select api10, sum(lateral_length_ft_exact) as len_ft from marts.nd_laterals_tile group by api10
)
select 'measured_bucket',
       (case when len_ft < 8000 then 1 when len_ft < 10000 then 2
             when len_ft < 10500 then 3 else 4 end),
       count(*), round(100.0 * count(*) / sum(count(*)) over (), 2)
  from t group by 2 order by 2;
SQL

cat "$rows"
awk -F'|' -v floor="${GW_BUCKET_MIN_SHARE_PCT:-15}" '
    $1 == "pinned_bucket"   { pinned++;   if ($4 + 0 < floor) pinned_fail++ }
    $1 == "measured_bucket" { measured++; if ($4 + 0 < floor) measured_fail++ }
    END {
        printf "VERDICT|LENGTH_BUCKETS pinned {7500,9500,11000}|%s %d of %d buckets under %d%%\n",
               (pinned_fail ? "FAIL" : "PASS"), pinned_fail + 0, pinned, floor;
        printf "VERDICT|LENGTH_BUCKETS measured {8000,10000,10500}|%s %d of %d buckets under %d%%\n",
               (measured_fail ? "FAIL" : "PASS"), measured_fail + 0, measured, floor;
    }' "$rows"
