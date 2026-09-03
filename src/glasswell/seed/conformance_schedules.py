"""Every cadence decision as an R8 rule: rows with a rationale, an effective date and evidence.

A schedule that exists only in a unit file is a mapping decision hidden in code, which is the
thing R8 forbids. Each job carries one `cr_job_cadence_<job_id>_1` rule, published through
`lineage.conformance_rule_publications` by the migration that ships this registry, and
`lineage.job_schedules.rule_id` points at it. The four platform rows carry no rule: their
cadence lives in their own unit's `OnCalendar=`, a tree artefact under review, and minting a
rule for it would duplicate the record rather than create one.

A cadence decision is never edited. Where one is corrected the `_1` row stands and a `_2` row
supersedes it at a later effective date, which is what `OBSERVE_DECISIONS` below carries for
the six Colorado rows the launch-posture ruling restated.

`stage` is `schedule` and `rule_kind` is `code_ref` -- the kind the glossary calls the honest
exception, where the decision is a row and named code carries it out.
"""

from __future__ import annotations

from datetime import date

import psycopg
from psycopg.types.json import Jsonb

from glasswell.seed.conformance_basins import MAPS_URL
from glasswell.seed.conformance_c115b import LAYER_URL as C115B_LAYER_URL
from glasswell.seed.conformance_co import CO_CADENCE_DECISIONS, CO_CADENCE_EVIDENCE
from glasswell.seed.conformance_fracfocus import DOWNLOAD_URL as FRACFOCUS_URL
from glasswell.seed.conformance_land import SERVICE_URL as PLSS_SERVICE_URL
from glasswell.seed.conformance_mt import GIS_PATHS_URL, PRODUCTION_URL
from glasswell.seed.conformance_nd import GIS_WELLS_URL as ND_GIS_URL
from glasswell.seed.conformance_nd import MPR_INDEX_URL
from glasswell.seed.conformance_nm import OCD_FTP_PAGE_URL
from glasswell.seed.conformance_nm_wells import GIS_LAYER_URL as NM_GIS_LAYER_URL
from glasswell.seed.conformance_tx import EWA_LINK, GIS_LINK
from glasswell.seed.schedules import (
    JOB_SOURCES,
    SCHEDULES,
    anchors,
    cadence_rule_id,
    observe_rule_id,
)

EFFECTIVE_FROM = date(2026, 9, 2)
# The symbol the planner really exports. `due_jobs` was a name nobody wrote, which is a
# published claim a reader cannot check -- the thing the register exists to prevent.
PLANNER = "glasswell.scheduler.plan:due_for"

# The one derivation every ingest cadence shares, stated once and cited by each rule that uses
# it, so a shorter policy on any one source shortens its job without a second decision.
INTERVAL_DERIVATION = "min(expected_poll_interval) over the job's lineage.job_sources rows"

_EVIDENCE: dict[str, str] = {
    "blm_plss_sections": PLSS_SERVICE_URL,
    "eia_sedimentary_basins": MAPS_URL,
    "fracfocus_csv": FRACFOCUS_URL,
    "mt_bogc_pru_production": PRODUCTION_URL,
    "mt_gis_well_paths": GIS_PATHS_URL,
    "nd_gis_directionals": ND_GIS_URL,
    "nd_mpr_xlsx": MPR_INDEX_URL,
    "nm_c115b_upstream": C115B_LAYER_URL,
    "nm_ocd_ogrid": OCD_FTP_PAGE_URL,
    "nm_ocd_wchistory": OCD_FTP_PAGE_URL,
    "nm_ocd_wellhistory": OCD_FTP_PAGE_URL,
    "nm_ocd_wells_gis": NM_GIS_LAYER_URL,
    "tx_gis_wells_county": GIS_LINK,
    "tx_wellbore_ewa_csv": EWA_LINK,
}

_DECISIONS: dict[str, dict[str, str]] = {
    "ingest_nd_gis": {
        "rule": "Pull the four NDIC OGD layers every 35 days, at the shortest interval any of"
        " them carries.",
        "rationale": "NDIC announces no republication schedule for the OGD shapefiles, so the"
        " cadence is glasswell's decision and not the publisher's. All four layers were"
        " registered at 35 days when the durable poll ledger was built, and the job takes the"
        " minimum over its four sources rather than a copy of one of them, so shortening any"
        " single policy shortens the job without a second decision being made anywhere.",
    },
    "ingest_nd_mpr": {
        "rule": "Request one production month on the 5th of each calendar month, at the lag the"
        " unit environment carries.",
        "rationale": "A 35-day interval fires about 10.4 times a year while NDIC files twelve"
        " production months, so roughly two months a year would never be requested and the"
        " freshness verdict would still call the source current. The retired timer already"
        " fired on the 5th; recording the calendar day rather than an interval is what makes"
        " the plan key the month and keeps every month asked for exactly once.",
    },
    "ingest_blm_plss": {
        "rule": "Pull townships and sections together every 35 days.",
        "rationale": "Both layers come from one BLM service in one pass, and both were"
        " registered at 35 days. Two jobs would race the same endpoint for no benefit, so the"
        " decision is one job over two sources, taking the minimum of their intervals.",
    },
    "ingest_nm_c115b": {
        "rule": "Pull the C-115B feature service on the 12th of each calendar month.",
        "rationale": "The retired C-115B timer fired on the 12th and the source is a monthly"
        " regulatory filing, so a calendar day is the honest shape and a 35-day interval would"
        " drift a month out of the year. The day is recorded here rather than in the unit so"
        " retiring the unit does not lose the decision.",
    },
    "ingest_fracfocus": {
        "rule": "Take the FracFocus archive when a release decides to, never on a tick.",
        "rationale": "The archive is 440 MB and is republished without notice or version, so a"
        " timed pull would trade a large download against no signal that anything changed. The"
        " release path already promotes the design at deploy time, which is the point at which"
        " someone is watching, so the cadence is owner-triggered and says so on screen.",
    },
    "ingest_mt_bogc": {
        "rule": "Load the Montana production archive by hand, never on a tick.",
        "rationale": "The load was measured at 74 MB down, 7.4 million rows, about an hour and"
        " two extra gigabytes of database. Montana publishes on the same 35-day rhythm as the"
        " North Dakota feeds, but a one-hour job under a shared six-hour tick budget is a"
        " scheduling decision that has to be taken deliberately, so it stays owner-triggered"
        " until the ledger carries measured peaks to size it from.",
    },
    "ingest_mt_gis": {
        "rule": "Pull the Montana surface and path layers every 35 days.",
        "rationale": "Both layers are registered at 35 days and the pull is measured in"
        " minutes, which is what makes the geometry half of Montana schedulable while the"
        " production half is not. This is the decision that puts marts.mt_wells on a"
        " computable next-due for the first time.",
    },
    "ingest_eia_boundaries": {
        "rule": "Pull the EIA basin and play boundary sets every 35 days.",
        "rationale": "Neither set had a poll policy at all, so the freshness verdict served"
        " cadence null and state pending permanently and no due time could be computed for"
        " either. EIA revises the boundary maps rarely and without notice; 35 days matches"
        " every other bulk boundary feed in the registry and costs 48 features per pull.",
    },
    "ingest_nm_ocd_stage": {
        "rule": "Stage the nine NM OCD tables by hand, never on a tick.",
        "rationale": "The FTP pull peaks at 2.24 GB across nine tables on a host with 5.5 GB"
        " left for ingest, and every one of the nine is registered owner-triggered because the"
        " publisher replaces the whole set at once. Staging and promotion are separate"
        " commands, so they are separate jobs with an edge between them.",
    },
    "ingest_nm_ocd_promote": {
        "rule": "Promote the staged NM OCD spine by hand, after the staging job has run.",
        "rationale": "Promotion is measured at 89 minutes and opens no socket, so its cost is"
        " database work rather than a download. It reacts to the staging job rather than to a"
        " clock, and stays owner-triggered while its input does.",
    },
    "ingest_nm_dims": {
        "rule": "Rebuild the NM dimensions by hand, after the promotion changed the spine.",
        "rationale": "The dimension build reads the promoted well-completion history and has no"
        " upstream of its own, so a clock could only guess. Its cadence is the promotion's,"
        " and the runbook's measured ceilings are what the row carries.",
    },
    "ingest_nm_wells": {
        "rule": "Promote the NM wells spine by hand, after the promotion changed the history.",
        "rationale": "The spine is derived from the staged well history rather than fetched, so"
        " the source it is filed under is the history table's own registry row and the trigger"
        " is the promotion that moved it.",
    },
    "ingest_nm_wells_gis": {
        "rule": "Pull the NM OCD wells feature service every 35 days.",
        "rationale": "A weekly refresh was recommended when the layer was registered and never"
        " chosen, so the source carried a null interval and nothing has ever run it. Thirty-five"
        " days is the interval every other feature-service source in the registry carries, and"
        " choosing it is what turns a recommendation into a schedule that can be measured.",
    },
    "ingest_tx_gis": {
        "rule": "Pull the Texas county well surface layer every 35 days.",
        "rationale": "The source was registered owner-triggered with a null interval, which"
        " made it permanently not due: the due rule cannot produce an instant without one. The"
        " RRC republishes the county extracts without notice, so 35 days is the same standing"
        " decision the other bulk feeds carry rather than a claim about the publisher.",
    },
    "ingest_tx_wellbore": {
        "rule": "Pull the Texas EWA wellbore extract every 35 days, bounded by the tick budget.",
        "rationale": "The same null interval left it never due. Its registered attempt timeout"
        " is twelve hours, which is longer than the scheduler unit's own six, so the job"
        " ceiling is the six-hour parent budget and a pull that needs longer has to be run by"
        " hand. Recording that here is what keeps the ceiling from being discovered by a"
        " SIGTERM mid-write.",
    },
    "marts_nd_wells": {
        "rule": "Refresh the ND wells mart when its GIS ingest reports changed input.",
        "rationale": "The mart is a projection: rebuilding it when nothing upstream changed"
        " burns the tick budget and produces an identical derivation. A code change is"
        " deliberately not a trigger, which is why the release path forces the refresh"
        " directly.",
    },
    "marts_nm_wells": {
        "rule": "Refresh the NM tile mart when the wells spine changes.",
        "rationale": "The retired unit ran this mart alone and never the New Mexico ingest, and"
        " that split is the decision being recorded: the ingest is owner-triggered, the mart"
        " reacts to it. Its measured ceilings are half the pipeline default, so the row carries"
        " them rather than inheriting a shared six-gigabyte cap.",
    },
    "marts_mt_wells": {
        "rule": "Refresh the MT wells mart when either Montana ingest changes.",
        "rationale": "The mart joins the geometry and production halves, which are on different"
        " cadences: one scheduled at 35 days, one owner-triggered. An edge to each is what"
        " gives the mart a computable next-due without asserting that both halves move"
        " together.",
    },
    "marts_tx_wells": {
        "rule": "Refresh the TX wells mart when either Texas ingest changes.",
        "rationale": "Nothing has ever refreshed this mart: it appears in no unit and no"
        " runbook step. Both its inputs are now on a 35-day cadence, so the mart follows them"
        " rather than carrying a clock of its own and rebuilding over unchanged rows.",
    },
    "marts_land_units": {
        "rule": "Refresh the land grid when the PLSS ingest reports changed input.",
        "rationale": "The grid is a projection of the two BLM layers loaded at the North Dakota"
        " extent. PLSS moves rarely, so a clock would rebuild an identical grid ten times a"
        " year; the change test is what makes the refresh evidence-driven.",
    },
    "marts_land_metrics": {
        "rule": "Refresh land metrics after the grid, and when either ND ingest changes.",
        "rationale": "Metrics join the grid to production and to well geometry, so three inputs"
        " can each move it. The edge to the grid is ordering rather than a change test, because"
        " metrics computed over a half-rebuilt grid would be published as though they were"
        " whole.",
    },
    "marts_cumulatives": {
        "rule": "Refresh cumulatives when a new production month lands.",
        "rationale": "Cumulatives stream 299 MB from the monthly production report and change"
        " only when it does, so the report month is the event. The release path already"
        " populates them once at deploy; this row is what keeps them current afterwards.",
    },
    "marts_neighbors": {
        "rule": "Rebuild the neighbour index after the wells mart, or on a design change.",
        "rationale": "The index builds a GiST index plus a primary key and a btree on temporary"
        " tables each refresh, which is why the host's maintenance work memory was raised for"
        " it; running it twice concurrently is the heaviest double-run hazard on the box. It is"
        " ordered after the wells mart and reacts to the completion design archive.",
    },
    "marts_basin_boundaries": {
        "rule": "Refresh the basin mart when the EIA download changes, under the postgres uid.",
        "rationale": "The refresh has only ever been run under the postgres identity, which is"
        " what the run_as column records rather than a claim that it must stay that way. The"
        " deploy now hands the marts functions to the pipeline role on every run, so the"
        " constraint may already be obsolete; the row states today's measured posture and the"
        " run ledger is what will let the next revision narrow it.",
    },
    "marts_jurisdiction_counts": {
        "rule": "Measure the jurisdiction well counts daily, after the wells marts.",
        "rationale": "The registry's served counts are measured, never asserted: the ledger is"
        " append-only and every row carries the derivation that produced it, so a jurisdiction"
        " with no measurement serves no number rather than a zero. Nothing wrote it -- there is"
        " no unit line and no deploy step -- so the ledger stood empty and every served count"
        " was unmeasured. Daily is the shortest cadence that is honest about a count whose"
        " inputs move on 35-day feeds, and the edges to the four wells marts keep a count from"
        " being taken over a mart that did not rebuild.",
    },
}

# What a launching row would have started unattended, one clause per job, so each successor
# argues its own cost rather than sharing a verdict.
_OBSERVE_CONSEQUENCE: dict[str, str] = {
    "co_ecmc_gis": "a pull of the three ECMC archives",
    "co_ecmc_production": "a pull of the rolling ECMC production file",
    "co_wells": "a promotion of the staged Colorado header table",
    "co_production": "a promotion of the staged rolling production file",
    "co_tiles": "a rebuild of the Colorado tile mart",
    "co_counts": "a re-measure of every jurisdiction's served well counts",
}

_OBSERVE_RULE = (
    "Compute this job's plan on every tick and record what would run, and launch nothing,"
    " until the launch flip lands."
)

_OBSERVE_RATIONALE = (
    "{predecessor} registered this row launch on the reasoning that Colorado installs no"
    " systemd unit, so no second runner could collide with it. That is true, and it is not the"
    " whole decision. plan.py:363 rewrites a due would_run entry to run for any row whose"
    " launch_mode is launch, runner.py:306 then starts it, and the deploy re-arms"
    " glasswell-scheduler.timer on every run, so this row turned the first unattended tick"
    " after a deploy into {consequence}. launch is the launch flip's own act rather than a"
    " per-jurisdiction registration choice, and the flip's preconditions are unmet: the two"
    " legacy pipeline timers are not retired, the deploy's Colorado mart steps 6c and 6d do not"
    " yet wait on scheduler runs instead of running the marts themselves, verify.sh does not"
    " yet assert the schedule a tick resolved, and no day of armed observe-mode ticks has been"
    " compared against what the legacy timers ran. This row observes until all four are met."
    " The flip is what appends the successor to this rule; nothing else may."
)

# Keyed by the successor's own rule id, because a job now carries more than one cadence
# decision and the builder has to know which of them it is writing.
OBSERVE_DECISIONS: dict[str, dict[str, object]] = {
    observe_rule_id(job_id): {
        "rule": _OBSERVE_RULE,
        "rationale": _OBSERVE_RATIONALE.format(
            predecessor=cadence_rule_id(job_id), consequence=consequence
        ),
        # The founding rule decided what drives the job; this one decides only the posture.
        "applies_to": ["job_schedules.launch_mode"],
    }
    for job_id, consequence in _OBSERVE_CONSEQUENCE.items()
}

SCHEDULE_RULES: tuple[dict[str, object], ...] = ()


# A later jurisdiction track declares its own cadence decisions beside its other rules and
# they are merged here, so one builder writes every cr_job_cadence_<job>_1 row and the grammar
# cannot fork.
EVIDENCE: dict[str, str] = {**_EVIDENCE, **CO_CADENCE_EVIDENCE}
DECISIONS: dict[str, dict[str, str]] = {**_DECISIONS, **CO_CADENCE_DECISIONS}

# One lookup for both generations, so the builder reads a rule id and never guesses an ordinal.
DECISIONS_BY_RULE: dict[str, dict[str, object]] = {
    **{cadence_rule_id(job_id): decision for job_id, decision in DECISIONS.items()},
    **OBSERVE_DECISIONS,
}

def _spec(job_id: str, schedule: dict[str, object], anchor: str) -> dict[str, object]:
    interval = schedule.get("cadence_interval")
    return {
        "job_id": job_id,
        "trigger": schedule["trigger"],
        "launch_mode": schedule.get("launch_mode", "observe"),
        "anchor_source_id": anchor,
        "sources": list(JOB_SOURCES.get(job_id, ())),
        "cadence_interval_days": interval.days if interval is not None else None,
        "cadence_monthly_on_day": schedule.get("cadence_monthly_on_day"),
        "interval_derivation": INTERVAL_DERIVATION if JOB_SOURCES.get(job_id) else None,
        "module_function": PLANNER,
        "contract_note": "The planner reads this row to decide whether the job is due; the"
        " decision is the row and the module only carries it out.",
    }


def _build() -> tuple[dict[str, object], ...]:
    anchor = anchors()
    rules: list[dict[str, object]] = []
    for schedule in SCHEDULES:
        job_id = str(schedule["job_id"])
        if schedule["trigger"] == "external_timer":
            continue
        rule_id = str(schedule.get("rule_id") or cadence_rule_id(job_id))
        founding = cadence_rule_id(job_id)
        decision = DECISIONS_BY_RULE[rule_id]
        source_id = anchor[job_id]
        rules.append(
            {
                "rule_id": rule_id,
                "supersedes_rule_id": None if rule_id == founding else founding,
                "effective_from": schedule.get("effective_from", EFFECTIVE_FROM),
                "source_id": source_id,
                "stage": "schedule",
                "rule_kind": "code_ref",
                "applies_to_fields": decision.get("applies_to", ["job_schedules.trigger"]),
                "spec": _spec(job_id, schedule, source_id),
                "rule": str(decision["rule"]),
                "rationale": str(decision["rationale"]),
                "evidence_url": EVIDENCE[source_id],
                "code_ref": "glasswell/scheduler/plan.py",
            }
        )
    return tuple(rules)


SCHEDULE_RULES = _build()

_INSERT = """
insert into lineage.conformance_rules
    (rule_id, rule_family, supersedes_rule_id, source_id, stage, applies_to_fields, rule_kind,
     spec, rule, rationale, evidence_url, code_ref, effective_from)
values (%(rule_id)s, %(rule_family)s, %(supersedes_rule_id)s, %(source_id)s, %(stage)s,
        %(applies_to_fields)s, %(rule_kind)s, %(spec)s, %(rule)s, %(rationale)s,
        %(evidence_url)s, %(code_ref)s, %(effective_from)s)
on conflict do nothing
"""


def _row(rule: dict[str, object]) -> dict[str, object]:
    rule_id = str(rule["rule_id"])
    return {
        **rule,
        "rule_family": rule_id.rsplit("_", 1)[0],
        "spec": Jsonb(rule["spec"]),
    }


def seed_conformance_schedules(connection: psycopg.Connection) -> int:
    """Rule ids are immutable: a cadence change is a new row, never an edit to this one."""
    with connection.cursor() as cursor:
        cursor.executemany(_INSERT, [_row(rule) for rule in SCHEDULE_RULES])
        cursor.execute(
            "select count(*) from lineage.conformance_rules where stage = 'schedule'"
        )
        return int(cursor.fetchone()[0])
