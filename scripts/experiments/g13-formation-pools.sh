#!/usr/bin/env bash
# G-13 — the formation_group signal, measured. Inventories staging.nd_mpr_oil.pool (the only
# formation signal that exists today), sizes the __other__ tail at candidate minimum counts,
# and shows that lineage.formation_aliases is empty and no formation_group column exists.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/experiments/lib.sh
. "$SCRIPT_DIR/lib.sh"

gw_header 'G-13 formation_group source signal (v0.6 §3.0.3 R8, SB-02 §4.4)'

rows="$(mktemp)"
trap 'rm -f "$rows"' EXIT

gw_psql <<'SQL' >"$rows"
select 'pool_inventory', count(*)::text, count(distinct upper(btrim(pool)))::text,
       count(distinct left(regexp_replace(api_wellno, '[^0-9]', '', 'g'), 10))::text, ''
  from staging.nd_mpr_oil;
select 'pool', pool, rows::text, wells::text, ''
  from (select upper(btrim(pool)) as pool, count(*) as rows,
               count(distinct left(regexp_replace(api_wellno, '[^0-9]', '', 'g'), 10)) as wells
          from staging.nd_mpr_oil group by 1) t
 order by t.wells desc, t.pool;   -- qualified: the text-cast output column shadows it otherwise
with p as (
  select upper(btrim(pool)) as pool,
         count(distinct left(regexp_replace(api_wellno, '[^0-9]', '', 'g'), 10)) as wells
    from staging.nd_mpr_oil
   where btrim(coalesce(pool, '')) <> ''
   group by 1
), tot as (select sum(wells) as s from p)
select 'min_count', t.thr::text,
       count(*) filter (where p.wells >= t.thr)::text,
       round(100.0 * sum(p.wells) filter (where p.wells >= t.thr) / max(tot.s), 2)::text,
       round(100.0 * coalesce(sum(p.wells) filter (where p.wells < t.thr), 0) / max(tot.s), 2)::text
  from p cross join (values (25), (50), (100), (200), (400)) t(thr) cross join tot
 group by t.thr order by t.thr;
select 'registry', 'lineage.formation_aliases rows', count(*)::text, '', '' from lineage.formation_aliases;
select 'registry', 'columns named %formation%',
       coalesce(string_agg(table_schema || '.' || table_name || '.' || column_name, ' '), 'none'), '', ''
  from information_schema.columns where column_name like '%formation%';
SQL

cat "$rows"
# Decision rule (pre-p3-gate.md §5): the __other__ floor is CAL_MIN_N, so a pool group too
# small to calibrate is not a group. The threshold row is read out of the measurement rather
# than restated, and the registry line is the E-2 precondition (gate-bgate m-4).
awk -F'|' -v thr="${GW_FORMATION_GROUP_MIN_COUNT:-100}" '
    $1 == "pool_inventory" { pools = $3 }
    $1 == "min_count" && $2 + 0 == thr + 0 { groups = $3; named = $4; other = $5 }
    $1 == "registry" && $2 ~ /formation_aliases/ { aliases = $3 }
    $1 == "registry" && $2 ~ /columns named/ { columns = $3 }
    END {
        if (groups == "") {
            printf "VERDICT|FORMATION_GROUP_MIN_COUNT|BLOCKED no measurement at %s wells\n", thr;
        } else {
            printf "VERDICT|FORMATION_GROUP_MIN_COUNT|MEASURED %s — %s of %s pools name a group, %s%% of wells named, __other__ %s%%\n",
                   thr, groups, pools, named, other;
        }
        printf "VERDICT|formation_group registry|%s lineage.formation_aliases holds %s row(s); columns named formation: %s\n",
               ((aliases + 0 == 0 || columns == "none") ? "BLOCKED" : "PASS"), aliases, columns;
    }' "$rows"
