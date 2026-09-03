/**
 * The three densest surfaces, rendered whole so a gate can read what they teach.
 *
 * Each one is built before the glossary is loaded, which is the order the app runs in: the map
 * and the status page mount from `renderView`, and `boot` fetches the index afterwards.
 */
import { createLayerPanel } from "../map/layer-panel.ts";
import { createLegend } from "../map/legend.ts";
import { defaultLayerSet } from "../map/registry.ts";
import { STATUS_VOCAB_RULES } from "../map/status.ts";
import { mountStatusPage, unmountStatusPage } from "../status-page/surface.ts";
import type { StatusPayload } from "../status-page/surface.ts";

export type SurfaceName = "map status legend" | "layers panel" | "status page";

export const SURFACE_NAMES: readonly SurfaceName[] = [
  "map status legend",
  "layers panel",
  "status page",
];

const COUNTED = { active: 12, plugged: 4, unmapped: 3 };
const HANDLES = { active: "drv_a", plugged: "drv_b", unmapped: "drv_c" };

/** Enough of a snapshot to draw every section; the contract fixture lives in surface.test.ts. */
export const STATUS_PAYLOAD: StatusPayload = {
  observed_at: "2026-08-26T18:00:00Z",
  snapshot_state: "current",
  state: "ok",
  checks: [
    {
      id: "api",
      label: "API",
      state: "ok",
      observed_at: "2026-08-26T18:00:00Z",
      detail: "The status request completed.",
      tier: "serving",
      probe: "this request",
    },
  ],
  datasets: [
    dataset("canonical.wells", "Wells", "well"),
    dataset("marts.nd_wells_tile", "ND well tiles", "well"),
    dataset("lineage.manifests", "Manifests", "artifact"),
  ],
  jobs: [
    {
      id: "ingest_nd_gis",
      label: "North Dakota GIS ingest",
      state: "ok",
      last_run_at: "2026-08-26T03:00:00Z",
      next_run_at: "2026-08-27T03:00:00Z",
      detail: "The timer is installed and the last run was persisted.",
      unit: "glasswell-ingest.timer",
      timer_armed: true,
      kind: "ingest",
      jurisdiction: "ND",
      cadence: "Every 35 days, the shortest interval its four sources carry",
      next_due_at: "2026-09-30T03:00:00Z",
      duration_seconds: 214,
      last_outcome: "would_run",
      refusal_code: null,
      refusal_class: null,
      launch_mode: "observe",
      schedule: {
        job_id: "ingest_nd_gis",
        effective_from: "2026-09-02",
        published_at: "2026-09-02",
        rule_id: "cr_job_cadence_ingest_nd_gis_1",
        rationale: "The four NDIC layers are pulled in one pass.",
        external_timer_unit: null,
        external_service_unit: null,
      },
    },
    {
      id: "marts_tx_wells",
      label: "Texas wells mart",
      state: "refused",
      last_run_at: null,
      next_run_at: null,
      detail: "This job is owner-triggered and is never due on a tick.",
      unit: null,
      timer_armed: null,
      kind: "mart",
      jurisdiction: "TX",
      cadence: "Refreshes when either Texas ingest changes",
      next_due_at: null,
      duration_seconds: null,
      last_outcome: "refused",
      refusal_code: "manual_only",
      refusal_class: "informational",
      launch_mode: "observe",
      schedule: {
        job_id: "marts_tx_wells",
        effective_from: "2026-09-02",
        published_at: "2026-09-02",
        rule_id: "cr_job_cadence_marts_tx_wells_1",
        rationale: "Nothing has ever refreshed this mart on a schedule.",
        external_timer_unit: null,
        external_service_unit: null,
      },
    },
    {
      id: "platform_backup",
      label: "Nightly backup",
      state: "ok",
      last_run_at: "2026-08-26T02:00:00Z",
      next_run_at: "2026-08-27T02:00:00Z",
      detail: "Timer is armed and the most recently completed run succeeded.",
      unit: "glasswell-backup.timer",
      timer_armed: true,
      kind: "maintenance",
      jurisdiction: null,
      cadence: null,
      next_due_at: null,
      duration_seconds: null,
      last_outcome: null,
      refusal_code: null,
      refusal_class: null,
      launch_mode: null,
      schedule: null,
    },
  ],
  sources: [
    {
      source_id: "nd_dmr_gis",
      name: "ND DMR GIS",
      state: "current",
      retrieval_vintage: "2026-08-20",
      declared_vintage: "2026-08-19",
      last_manifest_id: "man_abcdef",
      manifest_count: 12,
      last_attempt_at: "2026-08-26T02:00:00Z",
      last_outcome: "unchanged",
      next_expected_poll: "2026-09-02T02:00:00Z",
      cadence: "Weekly poll against a daily publisher",
      freshness_reason: "An unchanged check keeps the registered artifact current.",
    },
  ],
  platform: {
    code_version: "0.74",
    schema_version: 74,
    schema_version_reason: "Database migration identity, not a measured petroleum quantity.",
    database_bytes: 1024,
    database_bytes_reason: "Physical PostgreSQL storage inventory, not a petroleum figure.",
    edge_host: "glasswell.rpx.sh",
  },
  deployment: {
    public_origin: true,
    anonymous_reads: false,
    spa_served: true,
    basemap_served: true,
    tile_upstream: "configured",
    csp_report_only: false,
  },
  disclosures: [
    {
      id: "remote_copy",
      label: "Remote backup copy",
      state: "not_instrumented",
      detail: "The remote grant is write-only, so nothing here saw the far side.",
    },
  ],
};

export const statusEnvelope = { data: STATUS_PAYLOAD, meta: {} };

function dataset(id: string, label: string, grain: string): StatusPayload["datasets"][number] {
  return {
    dataset_id: id,
    label,
    scope: "North Dakota",
    grain,
    state: "available",
    counted_at: "2026-08-26T18:00:00Z",
    latest_knowledge_at: "2026-08-20",
    metrics: [
      {
        metric_id: `${id}.rows`,
        label: "Rows",
        value: 43_817,
        unit: "rows",
        precision: "exact",
        reason: "Operational inventory from a timed status snapshot, not a petroleum measurement.",
      },
    ],
    valid_from: "2015-05",
    valid_to: "2026-07",
    detail: "One row per well on the resident slice.",
  };
}

/** Builds one surface into `document.body` and hands back its root. */
export async function renderSurface(name: SurfaceName): Promise<HTMLElement> {
  if (name === "map status legend") return legendSurface();
  if (name === "layers panel") return panelSurface();
  return statusSurface();
}

function legendSurface(): HTMLElement {
  const legend = createLegend({ onFilter: () => {}, onExtent: () => {} });
  document.body.append(legend.element);
  legend.setCounts(COUNTED, 9, HANDLES, { wells: 19, handle: "drv_total" });
  legend.setVocabulary(STATUS_VOCAB_RULES.map((rule) => ({ rule, href: `/v1/conformance/${rule}` })));
  legend.setDrawn(17);
  legend.setProducing({
    counts: { producing: 9, not_producing: 4, unknown: 6 },
    handles: { producing: "drv_p", not_producing: "drv_n", unknown: "drv_u" },
    window: {
      months: 3,
      from: "2026-04",
      to: "2026-06",
      streams: ["oil", "gas"],
      liquids_basis: "oil plus condensate",
    },
    bbox: "-104,47,-102,48",
  });
  legend.setWellTypes({
    counts: { OG: 12, SWD: 3 },
    handles: { OG: "drv_wt1", SWD: "drv_wt2" },
    order: ["OG", "SWD"],
  });
  legend.setProvenance({
    counts: { surface: 19, lateral: 8, survey_trace: 2 },
    handles: { surface: "drv_g1", lateral: "drv_g2", survey_trace: "drv_g3" },
    order: ["surface", "lateral", "survey_trace"],
  });
  return legend.element;
}

function panelSurface(): HTMLElement {
  const panel = createLayerPanel({
    on: new Set(defaultLayerSet()),
    basemap: "dark",
    onToggle: () => {},
    onOpacity: () => {},
    onBasemap: () => {},
  });
  document.body.append(panel.element);
  panel.open();
  return panel.element;
}

async function statusSurface(): Promise<HTMLElement> {
  unmountStatusPage();
  const host = document.createElement("div");
  document.body.append(host);
  await mountStatusPage(host, { onForbidden: () => {} });
  return host;
}
