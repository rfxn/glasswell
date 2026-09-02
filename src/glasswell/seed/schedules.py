"""The job registry the scheduler resolves: what exists, what drives it, and what it needs.

Cadence used to be ten `ExecStart=` lines and a runbook sentence, so a registered source was
not a scheduled source and no query could tell which was which. These rows are the answer, and
every schedule row cites the `cr_job_cadence_*` conformance rule that decided it.

Every row seeded here is `launch_mode='observe'`: the two pipeline units stay armed through
v0.77, the tick records `would_run` and launches nothing, and v0.78 appends `launch` rows.
"""

from __future__ import annotations

from datetime import date, timedelta

import psycopg

from glasswell.lineage.errors import LineageError

REGISTERED_ON = date(2026, 9, 2)
INGEST_UNIT = "glasswell-ingest.service"
C115B_UNIT = "glasswell-c115b.service"


class ScheduleSeedError(LineageError):
    """The registry cannot be built as written, so it is refused rather than half-seeded."""


def cadence_rule_id(job_id: str) -> str:
    """One immutable rule id per job. Gate 4 pins the shape in both directions."""
    return f"cr_job_cadence_{job_id}_1"


REFUSAL_CODES: tuple[tuple[str, str, str], ...] = (
    (
        "manual_only",
        "informational",
        "This job is owner-triggered: it runs from glasswell-scheduler --run, never on a tick.",
    ),
    (
        "disabled",
        "informational",
        "The resolved schedule row is disabled, so the plan skips it deliberately.",
    ),
    (
        "externally_timed",
        "informational",
        "An external systemd timer owns this job; the scheduler observes it and never runs it.",
    ),
    (
        "requires_superuser",
        "informational",
        "This job needs a database identity the scheduler does not hold, so it stays a"
        " deploy step.",
    ),
    (
        "run_in_flight",
        "waiting",
        "A run of this job is still active, so this tick did not start a second one.",
    ),
    (
        "dependency_never_ran",
        "waiting",
        "A job this one depends on has never recorded a run, so there is nothing to react to.",
    ),
    (
        "deferred",
        "waiting",
        "The tick had less budget left than this job's timeout, so it waits for the next one.",
    ),
    (
        "dependency_failed",
        "fault",
        "A job this one depends on failed, and running on a failed input would publish it.",
    ),
    (
        "dependency_cycle",
        "fault",
        "This job sits in a dependency cycle, so no order over it exists to run.",
    ),
    (
        "upstream_unavailable",
        "fault",
        "The upstream this job reads could not be reached when the plan was computed.",
    ),
    (
        "entry_point_missing",
        "fault",
        "The registered entry point does not resolve to an importable module on this host.",
    ),
    (
        "scheduler_lost_unit",
        "fault",
        "The transient unit for a started run no longer exists, so its outcome is unknown.",
    ),
)

# job_id -> (kind, entry_point, argv, jurisdiction, run_as, rationale)
JOBS: tuple[dict[str, object], ...] = (
    {
        "job_id": "ingest_nd_gis",
        "label": "North Dakota GIS ingest",
        "kind": "ingest",
        "entry_point": "glasswell.ingest.nd_gis",
        "argv": ["--layer", "all"],
        "jurisdiction": "ND",
        "run_as": "glasswell",
        "rationale": "The four NDIC OGD shapefiles are pulled in one pass, which is why one"
        " job carries four job_sources rows and takes the shortest of their intervals.",
    },
    {
        "job_id": "ingest_nd_mpr",
        "label": "North Dakota production report",
        "kind": "ingest",
        "entry_point": "glasswell.ingest.nd_mpr",
        "argv": [],
        "jurisdiction": "ND",
        "run_as": "glasswell",
        "rationale": "The production month is derived at launch from the lag the unit"
        " environment carries, so no month literal is stored in argv and a re-run of the same"
        " plan row asks for the same month.",
    },
    {
        "job_id": "ingest_blm_plss",
        "label": "BLM land grid ingest",
        "kind": "ingest",
        "entry_point": "glasswell.ingest.blm_plss",
        "argv": ["--layer", "all"],
        "jurisdiction": "ND",
        "run_as": "glasswell",
        "rationale": "Townships and sections are one pull against one BLM service, so they are"
        " two sources on one job rather than two jobs racing the same endpoint.",
    },
    {
        "job_id": "ingest_nm_c115b",
        "label": "New Mexico C-115B capture",
        "kind": "ingest",
        "entry_point": "glasswell.ingest.nm_c115b",
        "argv": [],
        "jurisdiction": "NM",
        "run_as": "glasswell",
        "rationale": "The C-115B feature service is the New Mexico staging terminus and has"
        " always run on its own unit, so it is its own job with its own ceilings.",
    },
    {
        "job_id": "ingest_fracfocus",
        "label": "FracFocus archive ingest",
        "kind": "ingest",
        "entry_point": "glasswell.ingest.fracfocus",
        "argv": ["--promote-design"],
        "jurisdiction": None,
        "run_as": "glasswell",
        "rationale": "FracFocus covers the country rather than a jurisdiction, and the archive"
        " is republished without notice, so the release decides when to take it.",
    },
    {
        "job_id": "ingest_mt_bogc",
        "label": "Montana production ingest",
        "kind": "ingest",
        "entry_point": "glasswell.ingest.mt_bogc",
        "argv": [],
        "jurisdiction": "MT",
        "run_as": "glasswell",
        "rationale": "Well-grain and lease-grain production arrive in one archive, so they are"
        " two sources on one job; the load is measured at about an hour and two extra"
        " gigabytes, which is why it stays owner-triggered.",
    },
    {
        "job_id": "ingest_mt_gis",
        "label": "Montana GIS ingest",
        "kind": "ingest",
        "entry_point": "glasswell.ingest.mt_gis",
        "argv": [],
        "jurisdiction": "MT",
        "run_as": "glasswell",
        "rationale": "Surface points and well paths are one pull measured in minutes, which is"
        " what makes this half of Montana schedulable while the production half is not.",
    },
    {
        "job_id": "ingest_eia_boundaries",
        "label": "EIA boundary ingest",
        "kind": "ingest",
        "entry_point": "glasswell.ingest.eia_boundaries",
        "argv": [],
        "jurisdiction": None,
        "run_as": "glasswell",
        "rationale": "Basins and plays are one EIA download covering the whole country, so the"
        " job carries no jurisdiction and both sources hang off it.",
    },
    {
        "job_id": "ingest_nm_ocd_stage",
        "label": "New Mexico OCD staging",
        "kind": "ingest",
        "entry_point": "glasswell.ingest.nm_ocd",
        "argv": ["--stage-only"],
        "jurisdiction": "NM",
        "run_as": "glasswell",
        "rationale": "Staging and promotion are two commands, so they are two jobs and an edge"
        " between them; that is what keeps one transient unit, one timeout and one run row per"
        " process.",
    },
    {
        "job_id": "ingest_nm_ocd_promote",
        "label": "New Mexico OCD promotion",
        "kind": "ingest",
        "entry_point": "glasswell.ingest.nm_ocd",
        "argv": ["--promote-only"],
        "jurisdiction": "NM",
        "run_as": "glasswell",
        "rationale": "The promotion half reads what staging wrote and opens no socket, so it"
        " carries the same nine sources and a dependency on the staging job.",
    },
    {
        "job_id": "ingest_nm_dims",
        "label": "New Mexico dimensions",
        "kind": "ingest",
        "entry_point": "glasswell.ingest.nm_dims",
        "argv": [],
        "jurisdiction": "NM",
        "run_as": "glasswell",
        "rationale": "The dimension build reads the staged well-completion history, so its one"
        " source is the table it is derived from rather than a separate download.",
    },
    {
        "job_id": "ingest_nm_wells",
        "label": "New Mexico wells spine",
        "kind": "ingest",
        "entry_point": "glasswell.ingest.nm_wells",
        "argv": [],
        "jurisdiction": "NM",
        "run_as": "glasswell",
        "rationale": "The wells spine is promoted from the staged well history, which is the"
        " source its cadence is filed under.",
    },
    {
        "job_id": "ingest_nm_wells_gis",
        "label": "New Mexico wells GIS ingest",
        "kind": "ingest",
        "entry_point": "glasswell.ingest.nm_wells_gis",
        "argv": [],
        "jurisdiction": "NM",
        "run_as": "glasswell",
        "rationale": "A weekly refresh was recommended and never chosen, so nothing has ever"
        " run it; registering it is what turns that from a gap into a schedule.",
    },
    {
        "job_id": "ingest_tx_gis",
        "label": "Texas surface GIS ingest",
        "kind": "ingest",
        "entry_point": "glasswell.ingest.tx_gis",
        "argv": [],
        "jurisdiction": "TX",
        "run_as": "glasswell",
        "rationale": "The county surface pull has never been on a timer; its policy row"
        " carried no interval, so the due rule could not produce an instant for it.",
    },
    {
        "job_id": "ingest_tx_wellbore",
        "label": "Texas wellbore ingest",
        "kind": "ingest",
        "entry_point": "glasswell.ingest.tx_wellbore",
        "argv": [],
        "jurisdiction": "TX",
        "run_as": "glasswell",
        "rationale": "The EWA extract is the wellbore half of Texas and has never been on a"
        " timer either; the same null interval kept it permanently not due.",
    },
    {
        "job_id": "marts_nd_wells",
        "label": "North Dakota wells mart",
        "kind": "mart",
        "entry_point": "glasswell.marts.nd_wells",
        "argv": [],
        "jurisdiction": "ND",
        "run_as": "glasswell",
        "rationale": "The North Dakota wells mart is a projection of the GIS pull, so it reacts"
        " to that ingest rather than to a clock of its own.",
    },
    {
        "job_id": "marts_nm_wells",
        "label": "New Mexico wells mart",
        "kind": "mart",
        "entry_point": "glasswell.marts.nm_wells",
        "argv": [],
        "jurisdiction": "NM",
        "run_as": "glasswell",
        "rationale": "The New Mexico tile mart refreshes from the promoted wells spine; the"
        " retired unit ran the mart alone and never the ingest, and that split survives here.",
    },
    {
        "job_id": "marts_mt_wells",
        "label": "Montana wells mart",
        "kind": "mart",
        "entry_point": "glasswell.marts.mt_wells",
        "argv": [],
        "jurisdiction": "MT",
        "run_as": "glasswell",
        "rationale": "Montana's mart reads both the GIS and the production halves, so it"
        " carries an edge to each and refreshes when either changes.",
    },
    {
        "job_id": "marts_tx_wells",
        "label": "Texas wells mart",
        "kind": "mart",
        "entry_point": "glasswell.marts.tx_wells",
        "argv": [],
        "jurisdiction": "TX",
        "run_as": "glasswell",
        "rationale": "Nothing has ever refreshed the Texas mart on a schedule; it reads the"
        " surface and wellbore ingests, so it reacts to both.",
    },
    {
        "job_id": "marts_land_units",
        "label": "Land grid mart",
        "kind": "mart",
        "entry_point": "glasswell.marts.land_units",
        "argv": [],
        "jurisdiction": "ND",
        "run_as": "glasswell",
        "rationale": "The land grid is a projection of the BLM PLSS pull loaded at the North"
        " Dakota extent, which is the jurisdiction its sources are registered under.",
    },
    {
        "job_id": "marts_land_metrics",
        "label": "Land metrics mart",
        "kind": "mart",
        "entry_point": "glasswell.marts.land_metrics",
        "argv": [],
        "jurisdiction": "ND",
        "run_as": "glasswell",
        "rationale": "Land metrics joins the grid to production and geometry, so it waits on"
        " the land mart and on both North Dakota ingests.",
    },
    {
        "job_id": "marts_cumulatives",
        "label": "Cumulatives mart",
        "kind": "mart",
        "entry_point": "glasswell.marts.cumulatives",
        "argv": [],
        "jurisdiction": "ND",
        "run_as": "glasswell",
        "rationale": "Cumulatives stream from the monthly production report, so a new report"
        " month is the only event that changes them.",
    },
    {
        "job_id": "marts_neighbors",
        "label": "Neighbour index",
        "kind": "mart",
        "entry_point": "glasswell.marts.neighbors",
        "argv": [],
        "jurisdiction": None,
        "run_as": "glasswell",
        "rationale": "The neighbour index spans every registered jurisdiction and reads the"
        " completion design, so it carries no jurisdiction and waits on both inputs.",
    },
    {
        "job_id": "marts_basin_boundaries",
        "label": "Basin boundaries mart",
        "kind": "mart",
        "entry_point": "glasswell.marts.basin_boundaries",
        "argv": [],
        "jurisdiction": None,
        "run_as": "postgres",
        "rationale": "The basin refresh has only ever been run under the postgres identity;"
        " that is what run_as records, and it is the reason the scheduler runs as root and"
        " drops per job rather than holding one uid for all of them.",
    },
    {
        "job_id": "marts_jurisdiction_counts",
        "label": "Jurisdiction well counts",
        "kind": "mart",
        "entry_point": "glasswell.marts.counts",
        "argv": [],
        "jurisdiction": None,
        "run_as": "glasswell",
        "rationale": "The registry's served well counts come from an append-only ledger with"
        " no writer on any timer, so the ledger was empty and every served count unmeasured;"
        " this row is what makes the measurement scheduled.",
    },
    {
        "job_id": "platform_status",
        "label": "Status snapshot",
        "kind": "maintenance",
        "entry_point": "glasswell.status.collector",
        "argv": [],
        "jurisdiction": None,
        "run_as": None,
        "rationale": "The snapshot collector has its own timer and its own uid; the registry"
        " records it so the Status page lists it beside the data jobs, and never launches it.",
    },
    {
        "job_id": "platform_cf_ranges",
        "label": "Cloudflare range refresh",
        "kind": "maintenance",
        "entry_point": "/usr/local/sbin/refresh-ranges.sh",
        "argv": [],
        "jurisdiction": None,
        "run_as": None,
        "rationale": "The edge range refresh is a shell script under its own root unit, so it"
        " carries a path rather than a module and the registry decides nothing about its uid.",
    },
    {
        "job_id": "platform_lineage_retention",
        "label": "Lineage retention",
        "kind": "maintenance",
        "entry_point": "glasswell.lineage.retention",
        "argv": [],
        "jurisdiction": None,
        "run_as": None,
        "rationale": "The retention sweep runs on its own timer against its own unit; the row"
        " exists so the page can show its next elapse beside everything else.",
    },
    {
        "job_id": "platform_backup",
        "label": "Nightly backup",
        "kind": "maintenance",
        "entry_point": "/usr/local/sbin/glasswell-backup.sh",
        "argv": [],
        "jurisdiction": None,
        "run_as": None,
        "rationale": "The nightly dump is a shell script run by root; it is registered for"
        " visibility and the scheduler holds no opinion about when or as whom it runs.",
    },
)

NM_OCD_SOURCES = (
    "nm_ocd_ogrid",
    "nm_ocd_pod",
    "nm_ocd_podwc",
    "nm_ocd_pool",
    "nm_ocd_property",
    "nm_ocd_spacingunit",
    "nm_ocd_wchistory",
    "nm_ocd_wcproduction",
    "nm_ocd_wellhistory",
)

JOB_SOURCES: dict[str, tuple[str, ...]] = {
    "ingest_nd_gis": (
        "nd_gis_directionals",
        "nd_gis_horizontals_line",
        "nd_gis_spacing_units",
        "nd_gis_wells",
    ),
    "ingest_nd_mpr": ("nd_mpr_xlsx",),
    "ingest_blm_plss": ("blm_plss_sections", "blm_plss_townships"),
    "ingest_nm_c115b": ("nm_c115b_upstream",),
    "ingest_fracfocus": ("fracfocus_csv",),
    "ingest_mt_bogc": ("mt_bogc_pru_production", "mt_bogc_well_production"),
    "ingest_mt_gis": ("mt_gis_well_paths", "mt_gis_wells"),
    "ingest_eia_boundaries": ("eia_sedimentary_basins", "eia_shale_plays"),
    "ingest_nm_ocd_stage": NM_OCD_SOURCES,
    "ingest_nm_ocd_promote": NM_OCD_SOURCES,
    "ingest_nm_dims": ("nm_ocd_wchistory",),
    "ingest_nm_wells": ("nm_ocd_wellhistory",),
    "ingest_nm_wells_gis": ("nm_ocd_wells_gis",),
    "ingest_tx_gis": ("tx_gis_wells_county",),
    "ingest_tx_wellbore": ("tx_wellbore_ewa_csv",),
}

# A NOAA datum grid moves when the dependency pin moves, so there is no job to fetch it, and
# tx_pdq_dsv carries a policy row with no lineage.sources row at all. Both are named here
# rather than left to a membership check, so gate 1 stays a two-sided set equality.
UNJOBBED_SOURCES = frozenset({"proj_grid_nad27", "tx_pdq_dsv"})

DEPENDENCIES: tuple[tuple[str, str, str, str], ...] = (
    (
        "ingest_nm_ocd_promote",
        "ingest_nm_ocd_stage",
        "completed",
        "Promotion reads what staging wrote, so it waits on the staging run itself rather than"
        " on whether the upstream files changed.",
    ),
    (
        "ingest_nm_dims",
        "ingest_nm_ocd_promote",
        "changed",
        "The dimension build reads the promoted spine, so a promotion that changed nothing"
        " leaves it with nothing to rebuild.",
    ),
    (
        "ingest_nm_wells",
        "ingest_nm_ocd_promote",
        "changed",
        "The wells spine is promoted from the same staged history, so it reacts to a promotion"
        " that actually moved rows.",
    ),
    (
        "marts_nd_wells",
        "ingest_nd_gis",
        "changed",
        "The mart is a projection of the GIS pull and has nothing to do when the pull was"
        " unchanged.",
    ),
    (
        "marts_nm_wells",
        "ingest_nm_wells",
        "changed",
        "The tile mart reads the promoted wells spine.",
    ),
    (
        "marts_mt_wells",
        "ingest_mt_bogc",
        "changed",
        "Montana's mart reads the production half.",
    ),
    (
        "marts_mt_wells",
        "ingest_mt_gis",
        "changed",
        "Montana's mart reads the geometry half, and either half changing is a reason to"
        " rebuild.",
    ),
    (
        "marts_tx_wells",
        "ingest_tx_gis",
        "changed",
        "The Texas mart reads the county surface pull.",
    ),
    (
        "marts_tx_wells",
        "ingest_tx_wellbore",
        "changed",
        "The Texas mart reads the EWA wellbore extract as well, so either input changing"
        " rebuilds it.",
    ),
    (
        "marts_land_units",
        "ingest_blm_plss",
        "changed",
        "The land grid is a projection of the PLSS pull.",
    ),
    (
        "marts_land_metrics",
        "ingest_nd_gis",
        "changed",
        "Land metrics joins well geometry to the grid, so new geometry changes the metrics.",
    ),
    (
        "marts_land_metrics",
        "ingest_nd_mpr",
        "changed",
        "Land metrics carries production per unit, so a new report month changes it.",
    ),
    (
        "marts_land_metrics",
        "marts_land_units",
        "completed",
        "The grid must be rebuilt before the metrics over it are, so this edge is ordering and"
        " not a change test.",
    ),
    (
        "marts_cumulatives",
        "ingest_nd_mpr",
        "changed",
        "Cumulatives stream the monthly production report and change only when it does.",
    ),
    (
        "marts_neighbors",
        "ingest_fracfocus",
        "changed",
        "The neighbour index carries completion design from the FracFocus archive.",
    ),
    (
        "marts_neighbors",
        "marts_nd_wells",
        "completed",
        "The index is built over the wells mart, so it is ordered after it.",
    ),
    (
        "marts_basin_boundaries",
        "ingest_eia_boundaries",
        "changed",
        "The basin mart is a projection of the EIA download.",
    ),
    (
        "marts_jurisdiction_counts",
        "marts_mt_wells",
        "completed",
        "A count is only measured once the mart it counts has been rebuilt.",
    ),
    (
        "marts_jurisdiction_counts",
        "marts_nd_wells",
        "completed",
        "One edge per jurisdiction mart, so a state whose mart did not rebuild is not counted"
        " from stale rows.",
    ),
    (
        "marts_jurisdiction_counts",
        "marts_nm_wells",
        "completed",
        "New Mexico resolves its served status at read time, so the count reads the mart after"
        " it is rebuilt.",
    ),
    (
        "marts_jurisdiction_counts",
        "marts_tx_wells",
        "completed",
        "Texas is the fourth resident jurisdiction; a fifth adds an edge here rather than a"
        " code change.",
    ),
)

# job_id -> (trigger, interval, monthly_day, note, memory_max, timeout_seconds, legacy_unit)
SCHEDULES: tuple[dict[str, object], ...] = (
    {
        "job_id": "ingest_nd_gis",
        "trigger": "cadence",
        "cadence_interval": timedelta(days=35),
        "cadence_note": "Every 35 days, the shortest interval its four sources carry",
        "memory_max": "6G",
        "timeout_seconds": 3600,
        "legacy_unit": INGEST_UNIT,
    },
    {
        "job_id": "ingest_nd_mpr",
        "trigger": "cadence",
        "cadence_monthly_on_day": 5,
        "cadence_note": "The 5th of each month, one production month per fire at a 3-month lag",
        "memory_max": "2G",
        "timeout_seconds": 3600,
        "legacy_unit": INGEST_UNIT,
    },
    {
        "job_id": "ingest_blm_plss",
        "trigger": "cadence",
        "cadence_interval": timedelta(days=35),
        "cadence_note": "Every 35 days, matching both PLSS layer policies",
        "memory_max": "6G",
        "timeout_seconds": 3600,
        "legacy_unit": INGEST_UNIT,
    },
    {
        "job_id": "ingest_nm_c115b",
        "trigger": "cadence",
        "cadence_monthly_on_day": 12,
        "cadence_note": "The 12th of each month, the day the retired C-115B timer fired",
        "memory_max": "6G",
        "timeout_seconds": 3600,
        "legacy_unit": C115B_UNIT,
    },
    {
        "job_id": "ingest_fracfocus",
        "trigger": "manual",
        "cadence_note": "Owner-triggered; the release takes the archive with --promote-design",
        "memory_max": "6G",
        "timeout_seconds": 7200,
    },
    {
        "job_id": "ingest_mt_bogc",
        "trigger": "manual",
        "cadence_note": "Owner-triggered; measured at about an hour and two extra gigabytes",
        "memory_max": "6G",
        "timeout_seconds": 7200,
    },
    {
        "job_id": "ingest_mt_gis",
        "trigger": "cadence",
        "cadence_interval": timedelta(days=35),
        "cadence_note": "Every 35 days; the pull is measured in minutes",
        "memory_max": "6G",
        "timeout_seconds": 3600,
    },
    {
        "job_id": "ingest_eia_boundaries",
        "trigger": "cadence",
        "cadence_interval": timedelta(days=35),
        "cadence_note": "Every 35 days, the first cadence either EIA set has ever carried",
        "memory_max": "6G",
        "timeout_seconds": 3600,
    },
    {
        "job_id": "ingest_nm_ocd_stage",
        "trigger": "manual",
        "cadence_note": "Owner-triggered; the FTP pull peaks at 2.24 GB over nine tables",
        "memory_max": "6G",
        "timeout_seconds": 14400,
    },
    {
        "job_id": "ingest_nm_ocd_promote",
        "trigger": "manual",
        "cadence_note": "Owner-triggered; promotion is measured at 89 minutes",
        "memory_max": "6G",
        "timeout_seconds": 14400,
    },
    {
        "job_id": "ingest_nm_dims",
        "trigger": "manual",
        "cadence_note": "Owner-triggered; rebuilt from the staged well-completion history",
        "memory_max": "4G",
        "timeout_seconds": 1800,
    },
    {
        "job_id": "ingest_nm_wells",
        "trigger": "manual",
        "cadence_note": "Owner-triggered; promoted from the staged well history",
        "memory_max": "6G",
        "timeout_seconds": 3600,
    },
    {
        "job_id": "ingest_nm_wells_gis",
        "trigger": "cadence",
        "cadence_interval": timedelta(days=35),
        "cadence_note": "Every 35 days; a weekly refresh was recommended and never chosen",
        "memory_max": "6G",
        "timeout_seconds": 3600,
    },
    {
        "job_id": "ingest_tx_gis",
        "trigger": "cadence",
        "cadence_interval": timedelta(days=35),
        "cadence_note": "Every 35 days, the first interval this source has ever carried",
        "memory_max": "6G",
        "timeout_seconds": 3600,
    },
    {
        "job_id": "ingest_tx_wellbore",
        "trigger": "cadence",
        "cadence_interval": timedelta(days=35),
        "cadence_note": "Every 35 days; capped at the scheduler's own 6-hour parent budget",
        "memory_max": "6G",
        "timeout_seconds": 21600,
    },
    {
        "job_id": "marts_nd_wells",
        "trigger": "after_dependency",
        "cadence_note": "Refreshes when the North Dakota GIS pull changes",
        "memory_max": "6G",
        "timeout_seconds": 3600,
        "legacy_unit": INGEST_UNIT,
    },
    {
        "job_id": "marts_nm_wells",
        "trigger": "after_dependency",
        "cadence_note": "Refreshes when the New Mexico wells spine changes",
        "memory_max": "4G",
        "timeout_seconds": 1800,
        "legacy_unit": INGEST_UNIT,
    },
    {
        "job_id": "marts_mt_wells",
        "trigger": "after_dependency",
        "cadence_note": "Refreshes when either Montana ingest changes",
        "memory_max": "6G",
        "timeout_seconds": 3600,
        "legacy_unit": INGEST_UNIT,
    },
    {
        "job_id": "marts_tx_wells",
        "trigger": "after_dependency",
        "cadence_note": "Refreshes when either Texas ingest changes",
        "memory_max": "6G",
        "timeout_seconds": 3600,
    },
    {
        "job_id": "marts_land_units",
        "trigger": "after_dependency",
        "cadence_note": "Refreshes when the BLM land grid changes",
        "memory_max": "6G",
        "timeout_seconds": 3600,
        "legacy_unit": INGEST_UNIT,
    },
    {
        "job_id": "marts_land_metrics",
        "trigger": "after_dependency",
        "cadence_note": "Refreshes after the land grid, or when either ND ingest changes",
        "memory_max": "6G",
        "timeout_seconds": 3600,
        "legacy_unit": INGEST_UNIT,
    },
    {
        "job_id": "marts_cumulatives",
        "trigger": "after_dependency",
        "cadence_note": "Refreshes when a new production month lands",
        "memory_max": "2G",
        "timeout_seconds": 3600,
        "legacy_unit": INGEST_UNIT,
    },
    {
        "job_id": "marts_neighbors",
        "trigger": "after_dependency",
        "cadence_note": "Rebuilds after the wells mart, or when the design archive changes",
        "memory_max": "6G",
        "timeout_seconds": 3600,
        "legacy_unit": INGEST_UNIT,
    },
    {
        "job_id": "marts_basin_boundaries",
        "trigger": "after_dependency",
        "cadence_note": "Refreshes when the EIA boundary download changes",
        "memory_max": "4G",
        "timeout_seconds": 1800,
    },
    {
        "job_id": "marts_jurisdiction_counts",
        "trigger": "cadence",
        "cadence_interval": timedelta(days=1),
        "cadence_note": "Daily; the served counts are measured, never asserted",
        "memory_max": "2G",
        "timeout_seconds": 1800,
    },
    {
        "job_id": "platform_status",
        "trigger": "external_timer",
        "cadence_note": "Driven by its own timer; the scheduler reads its elapse, never runs it",
        "external_timer_unit": "glasswell-status.timer",
        "external_service_unit": "glasswell-status.service",
    },
    {
        "job_id": "platform_cf_ranges",
        "trigger": "external_timer",
        "cadence_note": "Driven by its own timer; the edge range file is rewritten by root",
        "external_timer_unit": "glasswell-cf-ranges.timer",
        "external_service_unit": "glasswell-cf-ranges.service",
    },
    {
        "job_id": "platform_lineage_retention",
        "trigger": "external_timer",
        "cadence_note": "Driven by its own timer; the sweep is bounded by the unit, not by us",
        "external_timer_unit": "glasswell-lineage-retention.timer",
        "external_service_unit": "glasswell-lineage-retention.service",
    },
    {
        "job_id": "platform_backup",
        "trigger": "external_timer",
        "cadence_note": "Driven by its own nightly timer; the dump runs outside the scheduler",
        "external_timer_unit": "glasswell-backup.timer",
        "external_service_unit": "glasswell-backup.service",
    },
)


def _dependencies_by_job() -> dict[str, tuple[str, ...]]:
    edges: dict[str, list[str]] = {}
    for job_id, depends_on, _trigger_on, _rationale in DEPENDENCIES:
        edges.setdefault(job_id, []).append(depends_on)
    return {job_id: tuple(sorted(names)) for job_id, names in edges.items()}


def resolve_anchor(job_id: str, *, _visiting: tuple[str, ...] = ()) -> str:
    """The source a job's cadence rule is filed under, walked to an ingest ancestor.

    An ingest job anchors on the least of its own sources. A mart anchors on the anchor of its
    first dependency by `depends_on_job_id`, which may itself be a mart, so the walk carries
    the path it came by: gate 2 guarantees every mart has *an* ingest neighbour, not that the
    first-dependency chain reaches one, and a two-mart cycle would otherwise recurse until the
    interpreter stopped it inside a deploy's own seed step.
    """
    if job_id in _visiting:
        cycle = " -> ".join((*_visiting, job_id))
        raise ScheduleSeedError(
            f"the anchor walk for {_visiting[0]} revisits {job_id}: {cycle}."
            " A dependency cycle has no ingest ancestor to anchor on."
        )
    sources = JOB_SOURCES.get(job_id, ())
    if sources:
        return min(sources)
    parents = _dependencies_by_job().get(job_id, ())
    if not parents:
        raise ScheduleSeedError(
            f"{job_id} has neither a source nor a dependency, so no anchor source exists"
        )
    return resolve_anchor(parents[0], _visiting=(*_visiting, job_id))


def anchors() -> dict[str, str]:
    """Every non-maintenance job's anchor, resolved once so the seed cannot disagree."""
    return {
        str(job["job_id"]): resolve_anchor(str(job["job_id"]))
        for job in JOBS
        if job["kind"] != "maintenance"
    }


_JOB_INSERT = """
insert into lineage.scheduled_jobs
    (job_id, label, kind, entry_point, argv, anchor_source_id, jurisdiction, run_as, rationale)
values (%(job_id)s, %(label)s, %(kind)s, %(entry_point)s, %(argv)s, %(anchor_source_id)s,
        %(jurisdiction)s, %(run_as)s, %(rationale)s)
on conflict do nothing
"""

_SOURCE_INSERT = """
insert into lineage.job_sources (job_id, source_id) values (%s, %s) on conflict do nothing
"""

_SCHEDULE_INSERT = """
insert into lineage.job_schedules
    (job_id, effective_from, published_at, rule_id, trigger, launch_mode, cadence_interval,
     cadence_monthly_on_day, cadence_note, memory_max, timeout_seconds, concurrency_group,
     enabled, legacy_unit, external_timer_unit, external_service_unit)
values (%(job_id)s, %(effective_from)s, %(published_at)s, %(rule_id)s, %(trigger)s,
        %(launch_mode)s, %(cadence_interval)s, %(cadence_monthly_on_day)s, %(cadence_note)s,
        %(memory_max)s, %(timeout_seconds)s, %(concurrency_group)s, %(enabled)s,
        %(legacy_unit)s, %(external_timer_unit)s, %(external_service_unit)s)
on conflict do nothing
"""

_DEPENDENCY_INSERT = """
insert into lineage.job_dependencies (job_id, depends_on_job_id, trigger_on, rationale)
values (%s, %s, %s, %s) on conflict do nothing
"""

_REFUSAL_INSERT = """
insert into lineage.refusal_codes (code, severity_class, sentence)
values (%s, %s, %s) on conflict do nothing
"""


def _job_row(job: dict[str, object], anchor: dict[str, str]) -> dict[str, object]:
    job_id = str(job["job_id"])
    return {**job, "anchor_source_id": anchor.get(job_id)}


def _schedule_row(schedule: dict[str, object]) -> dict[str, object]:
    job_id = str(schedule["job_id"])
    external = schedule["trigger"] == "external_timer"
    return {
        "job_id": job_id,
        "effective_from": REGISTERED_ON,
        "published_at": REGISTERED_ON,
        "rule_id": None if external else cadence_rule_id(job_id),
        "trigger": schedule["trigger"],
        # Every row this track seeds observes. v0.78 appends one launch row per job.
        "launch_mode": "observe",
        "cadence_interval": schedule.get("cadence_interval"),
        "cadence_monthly_on_day": schedule.get("cadence_monthly_on_day"),
        "cadence_note": schedule["cadence_note"],
        "memory_max": schedule.get("memory_max"),
        "timeout_seconds": schedule.get("timeout_seconds"),
        "concurrency_group": schedule.get("concurrency_group", "default"),
        "enabled": schedule.get("enabled", True),
        "legacy_unit": schedule.get("legacy_unit"),
        "external_timer_unit": schedule.get("external_timer_unit"),
        "external_service_unit": schedule.get("external_service_unit"),
    }


def seed_schedules(connection: psycopg.Connection) -> int:
    """Refusal vocabulary, jobs, sources, schedules and edges, in dependency order."""
    anchor = anchors()
    with connection.cursor() as cursor:
        cursor.executemany(_REFUSAL_INSERT, REFUSAL_CODES)
        cursor.executemany(_JOB_INSERT, [_job_row(job, anchor) for job in JOBS])
        cursor.executemany(
            _SOURCE_INSERT,
            [
                (job_id, source_id)
                for job_id, source_ids in sorted(JOB_SOURCES.items())
                for source_id in source_ids
            ],
        )
        cursor.executemany(_SCHEDULE_INSERT, [_schedule_row(row) for row in SCHEDULES])
        cursor.executemany(_DEPENDENCY_INSERT, DEPENDENCIES)
        cursor.execute("select count(*) from lineage.scheduled_jobs")
        return int(cursor.fetchone()[0])
