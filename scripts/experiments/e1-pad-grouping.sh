#!/usr/bin/env bash
# E-1 — pad-group chaining. Sweeps PAD_RADIUS_M x PAD_WINDOW_DAYS and reports the
# component-size distribution the 4A.3a guard fires on. Decision rule: the largest radius
# and window for which pad_group_max_share <= 0.02 and multi-well groups >= 10% of wells;
# if 150 m / 180 days satisfies both, the pinned values stand and this run ratifies them.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/experiments/lib.sh
. "$SCRIPT_DIR/lib.sh"

read -r -a eps_grid <<<"${GW_E1_RADII_M:-100 150 200 250 400}"
read -r -a gap_grid <<<"${GW_E1_WINDOWS_D:-90 180 365}"

rows="$(mktemp)"
trap 'rm -f "$rows"' EXIT

gw_header 'E-1 pad-group chaining (v0.6 4A.3a, SB-02 §3.4)'
printf 'eps_m|gap_days|wells|no_spud_date|multi_well_groups|wells_in_groups|max_group|p99_group|pad_group_max_share\n'

for eps in "${eps_grid[@]}"; do
    gw_int "$eps"
    for gap in "${gap_grid[@]}"; do
        gw_int "$gap"
        gw_psql -v "eps=$eps" -v "gap=$gap" <<'SQL'
with pts as (
  select w.api10, w.spud_date, st_transform(s.geom, 5070) as g
    from canonical.wells_latest w
    join canonical.well_spatial s on s.api10 = w.api10 and s.geom_type = 'surface'
), clustered as (
  select api10, spud_date,
         st_clusterdbscan(g, eps := :eps, minpoints := 2) over () as sc
    from pts
), lagged as (
  select api10, sc, spud_date,
         spud_date - lag(spud_date) over (partition by sc order by spud_date) as gap_days
    from clustered
   where sc is not null
), grouped as (
  select api10, sc, spud_date,
         sum(case when gap_days > :gap then 1 else 0 end)
           over (partition by sc order by spud_date
                 rows between unbounded preceding and current row) as sub
    from lagged
), sizes as (
  select sc, sub, count(*) as n from grouped group by sc, sub
)
select :eps, :gap,
       (select count(*) from pts),
       (select count(*) from pts where spud_date is null),
       count(*) filter (where n > 1),
       sum(n) filter (where n > 1),
       max(n),
       round(percentile_cont(0.99) within group (order by n)::numeric, 2),
       round(max(n)::numeric / (select count(*) from pts), 4)
  from sizes;
SQL
    done
done >"$rows"
cat "$rows"

awk -F'|' -v guard="${GW_PAD_GROUP_MAX_SHARE:-0.02}" -v floor="${GW_PAD_MIN_GROUP_FRACTION:-0.10}" '
    $1 == 150 && $2 == 180 {
        pass = ($9 + 0 <= guard && $5 + 0 >= floor * ($3 + 0)) ? "PASS" : "FAIL";
        printf "VERDICT|PAD_RADIUS_M=150 PAD_WINDOW_DAYS=180|%s max_share=%s multi_well_groups=%s of %s wells\n",
               pass, $9, $5, $3;
    }' "$rows"

# The fallback population: wells with no surface point or no date take
# (spacing_unit_id, completion half-year). Measured on the modelling population, not on the
# permit table, because an expired permit never enters a training set.
gw_psql <<'SQL'
select 'fallback_population',
       count(*) as wells_with_lateral,
       count(*) filter (where w.spud_date is null) as lateral_without_date,
       round(100.0 * count(*) filter (where w.spud_date is null) / count(*), 2) as pct
  from canonical.wells_latest w
 where w.api10 in (select distinct api10 from marts.nd_laterals_tile);
SQL
