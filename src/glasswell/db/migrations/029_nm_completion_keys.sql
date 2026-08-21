-- M_NM_DIM. P5.1 checked `\d canonical.well_completions` against the built schema before writing
-- this file: migration 022 shipped completion_key, api10, well_completion_pool and pool_reported
-- and none of pod_id, spacing_unit_id, property_id or source_operator_key. SB-01 §6.2's intended
-- DDL names pod_id; the table that exists does not. So 029 is required and it adds them.
--
-- It also has to move the grain, which P5.1 did not anticipate and the built schema forces.
-- 022 keys on (completion_key, source_id, production_month, report_vintage) with
-- production_month NOT NULL, because ND writes one completion row per completion-month beside
-- its production. NM's completion dimension comes from `wchistory`, which is effective-dated and
-- has no production month at all: 426,529 observations over 147,975 completions, exactly one of
-- them open (rec_termn_dte 9999-12-31) per completion. Filing an effective date in a column
-- named production_month would make a dimension row joinable to a production month it does not
-- describe, which is the silent wrong this project fails review over. So production_month
-- becomes nullable, the primary key becomes two partial unique indexes — one per grain — and a
-- CHECK requires every row to carry one of the two. ND's rows and ND's `on conflict do nothing`
-- are untouched: DO NOTHING with no conflict target arbitrates on every unique index, and every
-- ND row has a production_month, so it lands on the same key it landed on before.
--
-- pod_id is in the effective grain because NM's POD is stream-scoped. `pod` carries
-- pod_typ_cde G 58,107 / O 49,108 / W 36,678, and 71,435 (completion, eff_dte) groups in
-- `podwc` name more than one POD, every one of them a distinct POD. A TX lease is stream-scoped
-- too — SB-01 §6.2 keys canonical.leases on (oil_gas_code, district_no, lease_no) — so the
-- analogue holds including the fan-out, and a completion in three PODs is three rows rather than
-- one row with two PODs discarded by file order.

alter table canonical.well_completions add column api12                text;
alter table canonical.well_completions add column source_operator_key  text;
alter table canonical.well_completions add column pod_id               text;
alter table canonical.well_completions add column spacing_unit_id      text;
alter table canonical.well_completions add column property_id          text;
alter table canonical.well_completions add column status_reported      text;
alter table canonical.well_completions add column status_canonical     text;
alter table canonical.well_completions add column effective_from       date;

comment on column canonical.well_completions.api12 is
    'The API-12 wellbore suffix where the source carries one. NM does not: no in-scope NM OCD'
    ' table has a column past the api_st/api_cnty/api_well triple (cr_nm_wchistory_wellbore_policy_1).';
comment on column canonical.well_completions.source_operator_key is
    'The operator key exactly as the regulator issues it — OGRID for NM. Joins to'
    ' lineage.operator_aliases at confidence 1.0; never a name match.';
comment on column canonical.well_completions.pod_id is
    'NM POD (podwc crosswalk). Stream-scoped, so a completion may sit in several and each one'
    ' is its own row.';
comment on column canonical.well_completions.effective_from is
    'Knowledge-independent validity start for a dimension observation. Null for the'
    ' month-grained rows migration 022 shipped for ND.';

alter table canonical.well_completions drop constraint well_completions_pkey;
alter table canonical.well_completions alter column production_month drop not null;

create unique index well_completions_month_grain_uq
    on canonical.well_completions (completion_key, source_id, production_month, report_vintage)
    where production_month is not null;

-- coalesce rather than NULLS NOT DISTINCT: a null pod_id is one value here, the completion that
-- resolved no POD, and it must collide with itself or the append is not idempotent.
create unique index well_completions_effective_grain_uq
    on canonical.well_completions
       (completion_key, source_id, effective_from, coalesce(pod_id, ''), report_vintage)
    where production_month is null;

alter table canonical.well_completions add constraint well_completions_grain_check
    check (production_month is not null or effective_from is not null);

comment on constraint well_completions_grain_check on canonical.well_completions is
    'One of the two grains: a completion-month observation (ND) or an effective-dated dimension'
    ' observation (NM). A row with neither is an observation about nothing.';

create index well_completions_lease_equivalent_idx
    on canonical.well_completions (source_id, source_operator_key, well_completion_pool)
    where production_month is null;

create index well_completions_effective_idx
    on canonical.well_completions (api10, effective_from);

create or replace view canonical.well_completions_latest as
select completion_key, api10, well_completion_pool, pool_reported, source_id, production_month,
       report_vintage, source_manifest_id, derivation_id, created_at,
       api12, source_operator_key, pod_id, spacing_unit_id, property_id, status_reported,
       status_canonical, effective_from
  from (select c.*,
               row_number() over (
                   partition by completion_key, source_id, production_month,
                                coalesce(pod_id, '')
                   order by report_vintage desc, effective_from desc nulls last,
                            derivation_id desc) as vintage_rank
          from canonical.well_completions c) ranked
 where vintage_rank = 1;

comment on view canonical.well_completions_latest is
    'Latest known state per grain. effective_from orders inside a vintage so an effective-dated'
    ' dimension resolves to its newest observation rather than to whichever derivation_id sorted'
    ' last; ND rows all carry a null effective_from, so their ordering is what 022 gave them.';
