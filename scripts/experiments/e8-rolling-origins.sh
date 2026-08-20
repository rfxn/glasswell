#!/usr/bin/env bash
# E-8 — rolling-origin feasibility and the cum24 decision (OQ-1). Decision rule: an origin
# ships iff test_wells_cum12 >= 500; cum24 ships at P3 iff every shipping origin has
# test_wells_cum24 >= 500, otherwise ND ships the nine cum12 models only.
#
# The primary query counts producing months and therefore returns zero at every origin until
# E-0 lands. The projection uses spud dates on wells with a promoted lateral, which overstates
# the cohort by the spud-to-first-production lag and so is an upper bound.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/experiments/lib.sh
. "$SCRIPT_DIR/lib.sh"

gw_header 'E-8 rolling origins (SB-02 §3.5, OQ-1)'

rows="$(mktemp)"
trap 'rm -f "$rows"' EXIT

gw_psql <<'SQL' >"$rows"
select 'primary', b.b::text,
       count(*) filter (where n_pm >= 12)::text,
       count(*) filter (where n_pm >= 24)::text
  from (values (date '2021-01-01'), (date '2022-01-01'),
               (date '2023-01-01'), (date '2024-01-01')) b(b)
 cross join lateral (
   select count(*) as n_pm, min(production_month) as t_fp, api10
     from canonical.production_monthly_latest
    where stream = 'oil' and null_semantics in ('reported', 'reported_zero')
      and (volume > 0 or days_produced > 0)
    group by api10) w
 where w.t_fp >= b.b
 group by 1, 2 order by 2;
select 'projection', b.b::text,
       count(*) filter (where w.spud_date >= b.b and w.spud_date <= h.horizon - interval '12 months')::text,
       count(*) filter (where w.spud_date >= b.b and w.spud_date <= h.horizon - interval '24 months')::text
  from (values (date '2021-01-01'), (date '2022-01-01'),
               (date '2023-01-01'), (date '2024-01-01')) b(b)
 cross join canonical.wells_latest w
 cross join (select max(production_month) as horizon from canonical.production_monthly_latest) h
 where w.api10 in (select distinct api10 from marts.nd_laterals_tile)
 group by 1, 2 order by 2;
SQL

printf 'basis|origin|wells_cum12|wells_cum24\n'
cat "$rows"
awk -F'|' -v floor="${GW_ORIGIN_MIN_TEST_WELLS:-500}" '
    $1 == "primary" { origins++; if ($3 + 0 >= floor) c12++; if ($4 + 0 >= floor) c24++ }
    $1 == "projection" { porigins++; if ($3 + 0 >= floor) p12++; if ($4 + 0 >= floor) p24++ }
    END {
        printf "VERDICT|ROLLING_ORIGINS measured|%d of %d origins reach %d cum12 test wells\n",
               c12 + 0, origins, floor;
        printf "VERDICT|ROLLING_ORIGINS projected|%d of %d origins reach %d cum12, %d of %d reach cum24\n",
               p12 + 0, porigins, floor, p24 + 0, porigins;
        printf "VERDICT|OQ-1 cum24 at P3|%s\n",
               (p24 + 0 == porigins ? "cum24 ships" : "cum12 only — an origin is short of the cum24 floor");
    }' "$rows"
