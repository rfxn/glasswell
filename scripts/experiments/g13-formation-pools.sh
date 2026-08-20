#!/usr/bin/env bash
# G-13 — the formation_group signal, measured. Inventories staging.nd_mpr_oil.pool (the only
# formation signal that exists today), sizes the __other__ tail at candidate minimum counts,
# and shows that lineage.formation_aliases is empty and no formation_group column exists.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/experiments/lib.sh
. "$SCRIPT_DIR/lib.sh"

gw_header 'G-13 formation_group source signal (v0.6 §3.0.3 R8, SB-02 §4.4)'

gw_psql <<'SQL'
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
