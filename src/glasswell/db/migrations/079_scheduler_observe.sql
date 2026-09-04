-- The launch-posture ruling, as rows. 077 registered Colorado's six schedule rows
-- launch_mode='launch' on the reasoning that Colorado installs no systemd unit, so no second
-- runner could collide with them. That reasoning is sound and it is not the whole decision:
-- plan.py:363 rewrites a due would_run entry to run for a launching row, runner.py:306 starts
-- it, and deploy.sh re-arms glasswell-scheduler.timer on every deploy, so those six rows turned
-- the first unattended tick after a deploy into an ECMC pull and a mart rebuild. The host's
-- timer was stopped and disabled fifteen minutes before that tick and lineage.job_runs carries
-- no scheduler launch, so what this file corrects is a posture and not a run.
--
-- lineage.job_schedules is append-only on two clocks, so 077 is not edited and its rows stay
-- exactly what they registered. One superseding row per job is appended here instead, identical
-- to its founding row but for launch_mode and the rule it cites, at a strictly later
-- effective_from and published_at, so job_schedules_as_of resolves observe from the ruling's
-- date onward and 077 remains the record of what was decided on 2026-09-02.
--
-- launch is the launch-flip track's own act, never a per-jurisdiction registration choice. Each
-- successor rule cr_job_cadence_<job>_2 carries that argument, and the preconditions it is
-- waiting on, in served words.
--
-- REPOINT CHECKLIST (integrator, at the merge train):
--   1. evidence_tag UNRELEASED -> the tag that first carries these six successor rules. It
--      appears ONCE, at the conformance_rule_publications insert; every other statement reads
--      what it needs out of the rows it supersedes, so a half-repoint is not expressible here.
--   2. evidence_commit forty zeros -> the FIRST COMMIT ON MAIN THAT CONTAINS THESE RULE IDS,
--      which is the MERGE COMMIT of this track's PR and not the head it was written against.
--      scripts/release.py says so and tests/unit/test_release_tooling.py runs
--      `git grep -q <rule_id> <commit> -- src/` to prove it.
--   3. published_vintage 2026-09-03 -> the date the tag is cut. It is the successor rules' own
--      knowledge clock and is read against the host's today, so it must never be a date the
--      deploy host has not reached: a rule published in the future resolves nowhere and
--      /v1/conformance/<id> serves 404 for it.
--   4. The supersession's effective_from and published_at 2026-09-03 are NOT repoint fields.
--      They are the day the ruling was made and the host's scheduler timer was disarmed, and
--      moving them forward is the one edit that re-arms the hazard: job_schedules_as_of ranks
--      on effective_from, so a supersession the deploy host's today has not reached leaves
--      077's six launch rows resolving. They stay at or before the deploy's today, and strictly
--      after the founding rows' 2026-09-02.
--   5. seed/schedules.py OBSERVED_FROM -> the same date, in the same commit. The seed is the
--      second writer and tests/contract/test_schedule_parity.py holds the two copies together.
-- The rule ids are immutable and must not change during the repoint.

-- The evidence pair, written once for the six successors. 049's trigger refuses a conformance
-- rule whose publication is not registered, so this lands before the rules themselves and
-- before any seeder that carries them.
insert into lineage.conformance_rule_publications
    (rule_id, published_vintage, evidence_tag, evidence_commit)
select 'cr_job_cadence_' || job_id || '_2', date '2026-09-04', 'v0.80',
       'ed585501d39c75ed7cc6f4056ec7836067b4a5c1'
  from unnest(array[
       'co_ecmc_gis',
       'co_ecmc_production',
       'co_wells',
       'co_production',
       'co_tiles',
       'co_counts'
  ]::text[]) job_id
on conflict (rule_id) do nothing;

-- Guarded on the founding rule's residency exactly as 071's successor is, and for the same
-- reason: conformance_rules.source_id references lineage.sources, which migrate() never
-- populates, so on a fresh database this is a no-op and seed/conformance_schedules.py supplies
-- the pair. On a database that is already seeded -- the deployed one -- this is what lands the
-- successor, at migrate time rather than at the seed step that follows it.
--
-- Every field but the decision is read out of the row being superseded, so the successor cannot
-- disagree with its ancestor about the source, the evidence or the code that carries it out.
-- applies_to_fields is the exception and is deliberate: the founding rule decided what drives
-- the job, and this one decides only the posture.
insert into lineage.conformance_rules
    (rule_id, rule_family, supersedes_rule_id, source_id, stage, applies_to_fields, rule_kind,
     spec, rule, rationale, evidence_url, code_ref, effective_from)
select 'cr_job_cadence_' || j.job_id || '_2', prior.rule_family, prior.rule_id,
       prior.source_id, 'schedule',
       array['job_schedules.launch_mode']::text[], 'code_ref',
       jsonb_set(prior.spec, '{launch_mode}', '"observe"'::jsonb),
       'Compute this job''s plan on every tick and record what would run, and launch nothing,'
       ' until the launch flip lands.',
       prior.rule_id || ' registered this row launch on the reasoning that Colorado installs'
       ' no systemd unit, so no second runner could collide with it. That is true, and it is'
       ' not the whole decision. plan.py:363 rewrites a due would_run entry to run for any row'
       ' whose launch_mode is launch, runner.py:306 then starts it, and the deploy re-arms'
       ' glasswell-scheduler.timer on every run, so this row turned the first unattended tick'
       ' after a deploy into ' || j.consequence || '. launch is the launch flip''s own act'
       ' rather than a per-jurisdiction registration choice, and the flip''s preconditions are'
       ' unmet: the two legacy pipeline timers are not retired, the deploy''s Colorado mart'
       ' steps 6c and 6d do not yet wait on scheduler runs instead of running the marts'
       ' themselves, verify.sh does not yet assert the schedule a tick resolved, and no day of'
       ' armed observe-mode ticks has been compared against what the legacy timers ran. This'
       ' row observes until all four are met. The flip is what appends the successor to this'
       ' rule; nothing else may.',
       prior.evidence_url, prior.code_ref, date '2026-09-03'
  from (values
    ('co_ecmc_gis', 'a pull of the three ECMC archives'::text),
    ('co_ecmc_production', 'a pull of the rolling ECMC production file'::text),
    ('co_wells', 'a promotion of the staged Colorado header table'::text),
    ('co_production', 'a promotion of the staged rolling production file'::text),
    ('co_tiles', 'a rebuild of the Colorado tile mart'::text),
    ('co_counts', 'a re-measure of every jurisdiction''s served well counts'::text)
  ) as j(job_id, consequence)
  join lineage.conformance_rules prior
    on prior.rule_id = 'cr_job_cadence_' || j.job_id || '_1'
on conflict (rule_id) do nothing;

-- The supersession itself, copied from the founding row rather than restated, so "identical but
-- for the posture and the rule it cites" is a property of the statement and not a claim about
-- it. Guarded on the successor rule the line above lands, which is also what keeps this a no-op
-- on a fresh database: seed/schedules.py writes both rows there.
insert into lineage.job_schedules
    (job_id, effective_from, published_at, rule_id, trigger, launch_mode, cadence_interval,
     cadence_monthly_on_day, cadence_note, memory_max, timeout_seconds, concurrency_group,
     enabled, legacy_unit, external_timer_unit, external_service_unit)
select s.job_id, date '2026-09-03', date '2026-09-03',
       'cr_job_cadence_' || s.job_id || '_2', s.trigger, 'observe', s.cadence_interval,
       s.cadence_monthly_on_day, s.cadence_note, s.memory_max, s.timeout_seconds,
       s.concurrency_group, s.enabled, s.legacy_unit, s.external_timer_unit,
       s.external_service_unit
  from lineage.job_schedules s
 where s.job_id in ('co_ecmc_gis', 'co_ecmc_production', 'co_wells', 'co_production',
                    'co_tiles', 'co_counts')
   and s.effective_from = date '2026-09-02'
   and s.published_at = date '2026-09-02'
   and exists (select 1 from lineage.conformance_rules c
                where c.rule_id = 'cr_job_cadence_' || s.job_id || '_2')
on conflict do nothing;
