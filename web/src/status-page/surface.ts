import "./surface.css";

import { accountsSection, loadAccounts } from "../accounts/section.ts";
import { ApiError, getEnvelope } from "../api/client.ts";
import "../components/gw-count.ts";
import { labelElement } from "../glossary/gw-term.ts";
import { teach } from "../glossary/teach.ts";
import type { Teaching } from "../glossary/teach.ts";

export type SnapshotState = "current" | "stale" | "unavailable" | "invalid";
export type StatusState = "ok" | "degraded" | "partial";
export type CheckState = "ok" | "degraded" | "pending" | "unavailable" | "not_instrumented";
export type CheckTier = "serving" | "data" | "edge" | "host";

export interface StatusCheck {
  id: string;
  label: string;
  state: CheckState;
  observed_at: string | null;
  detail: string;
  tier: CheckTier | null;
  probe: string | null;
}

export interface StatusMetric {
  metric_id: string;
  label: string;
  value: number;
  unit: string;
  precision: "exact" | "estimated";
  reason: string;
}

export interface StatusDataset {
  dataset_id: string;
  label: string;
  scope: string;
  grain: string;
  state: "available" | "unavailable";
  counted_at: string | null;
  latest_knowledge_at: string | null;
  metrics: StatusMetric[];
  valid_from: string | null;
  valid_to: string | null;
  detail: string;
}

export interface StatusJob {
  id: string;
  label: string;
  state: CheckState;
  last_run_at: string | null;
  next_run_at: string | null;
  detail: string;
  unit: string | null;
  timer_armed: boolean | null;
}

export interface StatusSource {
  source_id: string;
  name: string;
  state: "current" | "stale" | "pending";
  retrieval_vintage: string | null;
  declared_vintage: string | null;
  last_manifest_id: string | null;
  manifest_count: number;
  last_attempt_at: string | null;
  last_outcome: "attempted" | "new" | "unchanged" | "failed" | "interrupted" | null;
  next_expected_poll: string | null;
  cadence: string | null;
  freshness_reason: string;
}

export interface StatusPayload {
  observed_at: string | null;
  snapshot_state: SnapshotState;
  state: StatusState;
  checks: StatusCheck[];
  datasets: StatusDataset[];
  jobs: StatusJob[];
  sources: StatusSource[];
  platform: {
    code_version: string | null;
    schema_version: number | null;
    schema_version_reason: string;
    database_bytes: number | null;
    database_bytes_reason: string;
    edge_host: string | null;
  };
  deployment: {
    public_origin: boolean;
    anonymous_reads: boolean;
    spa_served: boolean;
    basemap_served: boolean;
    tile_upstream: "default" | "configured";
    csp_report_only: boolean;
  } | null;
  disclosures: {
    id: string;
    label: string;
    state: "not_instrumented" | "limited";
    detail: string;
  }[];
}

export interface StatusPageOptions {
  onForbidden(error: ApiError): void;
  /**
   * The role `main.ts` already resolved, not a second probe: Accounts renders for an owner and
   * for nobody else, and an absent role is nobody.
   */
  role?: string | null;
}

interface Mount {
  host: HTMLElement;
  options: StatusPageOptions;
  controller: AbortController | null;
  teaching: Teaching;
}

const SNAPSHOT_LABELS: Record<SnapshotState, string> = {
  current: "Current snapshot",
  stale: "Stale snapshot",
  unavailable: "Snapshot unavailable",
  invalid: "Snapshot invalid",
};

const STATE_LABELS: Record<StatusState | CheckState | StatusSource["state"], string> = {
  ok: "OK",
  degraded: "Degraded",
  partial: "Partial",
  pending: "Pending",
  unavailable: "Unavailable",
  not_instrumented: "Not instrumented",
  current: "Current",
  stale: "Stale",
};

const MANIFEST_COUNT_REASON =
  "Registered manifest count is provenance bookkeeping about source artifacts, not a petroleum measurement.";

const OUTCOME_LABELS: Record<NonNullable<StatusSource["last_outcome"]>, string> = {
  attempted: "Attempted",
  new: "New artifact",
  unchanged: "Unchanged",
  failed: "Failed",
  interrupted: "Interrupted",
};

const TIERS: { id: CheckTier | null; label: string }[] = [
  { id: "serving", label: "Serving plane" },
  { id: "data", label: "Data plane" },
  { id: "edge", label: "Edge" },
  { id: "host", label: "Host" },
  { id: null, label: "Unclassified" },
];

/** The storage layer a dataset lives in is vocabulary, but it is written as an identifier. */
const LAYERS: { prefix: string; label: string; term: string | null }[] = [
  { prefix: "canonical.", label: "canonical", term: "gt_canonical" },
  { prefix: "marts.", label: "marts", term: "gt_marts" },
  { prefix: "lineage.", label: "lineage", term: "gt_lineage" },
];

type Posture = NonNullable<StatusPayload["deployment"]>;

const POSTURE: { label: string; value(posture: Posture): Node }[] = [
  { label: "Origin", value: (one) => textValue(one.public_origin ? "Public" : "Closed network") },
  { label: "Anonymous reads", value: (one) => anonymousValue(one.anonymous_reads) },
  {
    label: "Tile upstream",
    value: (one) => textValue(one.tile_upstream === "configured" ? "Configured" : "Default"),
  },
  { label: "Frontend bundle", value: (one) => servedValue(one.spa_served) },
  { label: "Local basemap", value: (one) => servedValue(one.basemap_served) },
  { label: "CSP", value: (one) => textValue(one.csp_report_only ? "Report-only" : "Enforced") },
];

/**
 * Method statements that qualify a section rather than report its state. They stay one click
 * away instead of standing above the facts a reader came for.
 */
const NOTES = {
  architecture: {
    summary: "What a check proves",
    text: "A successful check proves only the detail it names. Capacity, replication, and host services are not inferred from a database query. A component with no probe is listed as not instrumented rather than omitted.",
  },
  footprint: {
    summary: "How these counts are grained",
    text: "Each row states its grain, and its precision is exact unless a metric is marked Estimated. Unrelated row populations are never summed into a single records total, so there is no headline total here on purpose. Counts are taken at the snapshot's observation time.",
  },
  jobs: {
    summary: "What a run time means",
    text: "Run times are reported only where the platform persists them; an installed timer is not treated as proof that a job completed. An armed timer states that the schedule exists, never that the last run succeeded.",
  },
  sources: {
    summary: "How freshness is decided",
    text: "Each state combines independently committed poll evidence, the registered artifact, and one source-specific cadence. Unchanged checks can keep older bytes current; failed or interrupted checks cannot.",
  },
  disclosures: {
    summary: "Why this section exists",
    text: "Unknowns stay visible instead of being folded into a healthy summary.",
  },
} as const;

let mounted: Mount | null = null;

export function unmountStatusPage(): void {
  if (!mounted) return;
  mounted.controller?.abort();
  mounted.teaching.release();
  mounted.host.removeAttribute("aria-busy");
  mounted.host.replaceChildren();
  mounted = null;
}

export async function mountStatusPage(
  host: HTMLElement,
  options: StatusPageOptions,
): Promise<void> {
  unmountStatusPage();
  // The surface is public and paints before boot has the index, so it waits for one.
  const mount: Mount = { host, options, controller: null, teaching: teach(host) };
  mounted = mount;
  await refresh(mount);
}

async function refresh(mount: Mount, restoreFocus = false): Promise<void> {
  mount.controller?.abort();
  const controller = new AbortController();
  mount.controller = controller;
  renderLoading(mount.host);

  try {
    const envelope = await getEnvelope<unknown>("/v1/status", {}, controller.signal);
    const payload = statusPayload(envelope.data);
    if (mounted !== mount || controller.signal.aborted) return;
    const rendered = renderStatus(mount, payload);
    if (restoreFocus) focusRefresh(mount);
    // The page is already on screen; this awaits the section's own two requests so a caller --
    // and a test -- can tell when the surface has finished, not when it first painted.
    await rendered;
  } catch (error) {
    if (mounted !== mount || controller.signal.aborted || aborted(error)) return;
    const forbidden = error instanceof ApiError && error.problem.status === 403;
    if (forbidden) mount.options.onForbidden(error);
    renderError(mount, error);
    if (restoreFocus && !forbidden) focusRefresh(mount);
  } finally {
    if (mounted === mount && mount.controller === controller) {
      mount.controller = null;
      mount.host.setAttribute("aria-busy", "false");
    }
  }
}

function renderLoading(host: HTMLElement): void {
  host.setAttribute("aria-busy", "true");
  const root = pageRoot();
  root.append(pageHeader(), loadingSection("Checking infrastructure and dataset inventory…"));
  host.replaceChildren(root);
}

function renderError(mount: Mount, error: unknown): void {
  const root = pageRoot();
  root.append(pageHeader());

  const section = element("section", "gw-status-error");
  section.setAttribute("aria-labelledby", "gw-status-error-title");
  const title = element("h2", "gw-status-section-title");
  title.id = "gw-status-error-title";
  const detail = element("p", "gw-status-error-detail");

  if (error instanceof ApiError) {
    title.textContent = error.problem.status === 403 ? "Status access required" : "Status unavailable";
    detail.textContent = `${error.problem.title} (HTTP ${error.problem.status}).`;
    if (error.problem.request_id) {
      const request = element("p", "gw-status-request-id");
      request.textContent = `Request ${error.problem.request_id}`;
      section.append(title, detail, request);
    } else {
      section.append(title, detail);
    }
  } else {
    title.textContent =
      error instanceof StatusContractError || error instanceof SyntaxError
        ? "Status response is invalid"
        : "Status unavailable";
    detail.textContent = error instanceof Error ? error.message : String(error);
    section.append(title, detail);
  }

  const retry = document.createElement("button");
  retry.type = "button";
  retry.className = "gw-status-refresh";
  retry.textContent = "Retry";
  retry.setAttribute("data-no-glossary", "");
  retry.addEventListener("click", () => void refresh(mount, true));
  section.append(retry);
  root.append(section);
  mount.host.replaceChildren(root);
  mount.teaching.retouch();
}

function renderStatus(mount: Mount, payload: StatusPayload): Promise<void> | undefined {
  const root = pageRoot();
  const header = pageHeader();
  const refreshButton = document.createElement("button");
  refreshButton.type = "button";
  refreshButton.className = "gw-status-refresh";
  refreshButton.textContent = "Refresh";
  refreshButton.setAttribute("data-no-glossary", "");
  refreshButton.addEventListener("click", () => void refresh(mount, true));
  header.append(refreshButton);

  const announcement = element("p", "gw-status-announcement");
  announcement.setAttribute("role", "status");
  announcement.textContent = `${SNAPSHOT_LABELS[payload.snapshot_state]}. Status updated.`;

  const accounts = accountsSection(mount.options.role);
  root.append(
    header,
    deployment(payload),
    architecture(payload),
    footprint(payload),
    jobs(payload),
    sources(payload.sources),
    disclosures(payload.disclosures),
    ...(accounts ? [accounts] : []),
    announcement,
  );
  mount.host.replaceChildren(root);
  mount.teaching.retouch();
  if (!accounts) return undefined;
  // The section fills after this paint, and its rows carry the vocabulary the glossary now
  // defines (Session, Role, Viewer, Owner), so the teaching layer has to reach them as well.
  return loadAccounts(accounts).then(() => mount.teaching.retouch());
}

function pageRoot(): HTMLElement {
  return element("div", "gw-status-page");
}

function pageHeader(): HTMLElement {
  const header = element("header", "gw-status-page-head");
  const copy = element("div", "gw-status-page-copy");
  const eyebrow = element("p", "gw-status-eyebrow");
  eyebrow.textContent = "Operational visibility";
  const title = document.createElement("h1");
  title.textContent = "Status";
  copy.append(eyebrow, title);
  header.append(copy);
  return header;
}

function loadingSection(message: string): HTMLElement {
  const section = element("section", "gw-status-loading");
  section.setAttribute("role", "status");
  const pulse = element("span", "gw-status-loading-mark");
  pulse.setAttribute("aria-hidden", "true");
  const copy = document.createElement("p");
  copy.textContent = message;
  section.append(pulse, copy);
  return section;
}

function deployment(payload: StatusPayload): HTMLElement {
  const section = element("section", "gw-status-summary");
  section.dataset["snapshot"] = payload.snapshot_state;
  section.setAttribute("aria-labelledby", "gw-status-summary-title");

  const heading = element("div", "gw-status-summary-head");
  const title = element("h2", "gw-status-section-title");
  title.id = "gw-status-summary-title";
  title.textContent = "Deployment";
  heading.append(
    title,
    badge(SNAPSHOT_LABELS[payload.snapshot_state], payload.snapshot_state),
    badge(STATE_LABELS[payload.state], payload.state),
  );
  section.append(heading);

  if (payload.snapshot_state !== "current") {
    const warning = element("p", "gw-status-snapshot-note");
    warning.textContent = snapshotMessage(payload.snapshot_state);
    section.append(warning);
  }

  const facts = element("dl", "gw-status-facts");
  summaryFact(facts, "Code version", textValue(payload.platform.code_version ?? "Unavailable", true));
  summaryFact(
    facts,
    "Schema head",
    payload.platform.schema_version === null
      ? textValue("Unavailable")
      : countedValue(
          payload.platform.schema_version,
          "migration",
          payload.platform.schema_version_reason,
        ),
  );
  summaryFact(facts, "Edge host", textValue(payload.platform.edge_host ?? "Not served", true));
  summaryFact(facts, "Observed", timeOrFallback(payload.observed_at, "Not observed"));
  summaryFact(
    facts,
    "Database storage",
    payload.platform.database_bytes === null
      ? textValue("Unavailable")
      : countedValue(
          payload.platform.database_bytes,
          "bytes",
          payload.platform.database_bytes_reason,
        ),
  );

  const posture = payload.deployment;
  for (const item of POSTURE) {
    summaryFact(facts, item.label, posture === null ? textValue("Not served") : item.value(posture));
  }

  section.append(facts);
  return section;
}

function architecture(payload: StatusPayload): HTMLElement {
  const section = sectionWithTitle("gw-status-checks-title", "Architecture", NOTES.architecture);
  if (payload.checks.length === 0) {
    section.append(emptyBlock("No components were served."));
    return section;
  }
  for (const tier of TIERS) {
    const members = payload.checks.filter((check) => check.tier === tier.id);
    if (members.length === 0) continue;
    const group = element("h3", "gw-status-tier");
    group.textContent = tier.label;
    const list = element("ul", "gw-status-card-grid gw-status-check-grid");
    for (const check of members) {
      const state = effectiveState(check.state, payload.snapshot_state);
      const item = document.createElement("li");
      item.className = "gw-status-card gw-status-check";
      const head = element("div", "gw-status-card-head");
      const title = document.createElement("h4");
      title.textContent = check.label;
      head.append(title, badge(STATE_LABELS[state], state));
      const probe = element("p", "gw-status-probe");
      probe.append(check.probe === null ? textValue("No probe registered") : textValue(check.probe, true));
      const detail = document.createElement("p");
      detail.textContent = check.detail;
      item.append(head, probe, detail);
      if (check.observed_at !== payload.observed_at) {
        const observed = element("p", "gw-status-card-time");
        observed.append("Observed ", timeOrFallback(check.observed_at, "not recorded"));
        item.append(observed);
      }
      list.append(item);
    }
    section.append(group, list);
  }
  return section;
}

function footprint(payload: StatusPayload): HTMLElement {
  const section = sectionWithTitle("gw-status-datasets-title", "Data footprint", NOTES.footprint);
  const wrapper = element("div", "gw-status-table-wrap");
  const table = document.createElement("table");
  table.className = "gw-status-table gw-status-footprint";
  const caption = document.createElement("caption");
  caption.textContent = "Resident inventory by storage layer, each row on its own stated grain";
  const head = tableHead(["Dataset", "Scope", "Grain", "Magnitude", "Covers", "Latest knowledge"]);
  const body = document.createElement("tbody");

  for (const layer of layersOf(payload.datasets)) {
    body.append(layerRow(layer.label, layer.term, layer.items.length));
    for (const dataset of layer.items) body.append(footprintRow(dataset));
  }
  if (payload.datasets.length === 0) {
    body.append(emptyTableRow(6, "No dataset inventory was served."));
  }
  table.append(caption, head, body);
  wrapper.append(table);
  section.append(wrapper);
  return section;
}

interface LayerGroup {
  label: string;
  term: string | null;
  items: StatusDataset[];
}

function layersOf(items: StatusDataset[]): LayerGroup[] {
  const grouped: LayerGroup[] = LAYERS.map((layer) => ({
    label: layer.label,
    term: layer.term,
    items: items.filter((dataset) => dataset.dataset_id.startsWith(layer.prefix)),
  }));
  const rest = items.filter(
    (dataset) => !LAYERS.some((layer) => dataset.dataset_id.startsWith(layer.prefix)),
  );
  if (rest.length > 0) grouped.push({ label: "other", term: null, items: rest });
  return grouped.filter((layer) => layer.items.length > 0);
}

function layerRow(label: string, term: string | null, count: number): HTMLTableRowElement {
  const row = element("tr", "gw-status-layer-row");
  const cell = document.createElement("th");
  cell.scope = "colgroup";
  cell.colSpan = 6;
  const name = document.createElement("code");
  name.textContent = label;
  cell.append(codeTerm(name, term), ` · ${count} ${count === 1 ? "dataset" : "datasets"}`);
  row.append(cell);
  return row;
}

/** The highlighter skips code spans, so an identifier that is also vocabulary is bound by hand. */
function codeTerm(code: HTMLElement, termId: string | null): HTMLElement {
  if (!termId) return code;
  const term = document.createElement("gw-term");
  term.setAttribute("term-id", termId);
  term.append(code);
  return term;
}

function footprintRow(dataset: StatusDataset): HTMLTableRowElement {
  const row = document.createElement("tr");
  const name = document.createElement("th");
  name.scope = "row";
  name.append(document.createTextNode(dataset.label));
  const id = document.createElement("code");
  id.textContent = dataset.dataset_id;
  name.append(id, datasetNote(dataset));

  const grain = document.createElement("td");
  grain.append(textValue(dataset.grain));
  const shared = sharedPrecision(dataset);
  if (shared !== null) grain.append(precisionBadge(shared));

  const magnitudes = element("ul", "gw-status-magnitudes");
  for (const metric of dataset.metrics) {
    const item = document.createElement("li");
    const label = element("span", "gw-status-magnitude-label");
    label.textContent = metric.label;
    item.append(label, countedValue(metric.value, metric.unit, metric.reason));
    if (shared === null) item.append(precisionBadge(metric.precision));
    magnitudes.append(item);
  }
  const magnitudeCell = document.createElement("td");
  magnitudeCell.append(dataset.metrics.length === 0 ? textValue("None served") : magnitudes);

  row.append(
    name,
    tableCell(
      dataset.state === "available"
        ? textValue(dataset.scope)
        : badge("Unavailable", dataset.state),
    ),
    grain,
    magnitudeCell,
    tableCell(span(dataset)),
    tableCell(timeOrFallback(dataset.latest_knowledge_at, "Not recorded")),
  );
  return row;
}

function sharedPrecision(dataset: StatusDataset): StatusMetric["precision"] | null {
  const first = dataset.metrics[0];
  if (first === undefined) return null;
  return dataset.metrics.every((metric) => metric.precision === first.precision)
    ? first.precision
    : null;
}

function precisionBadge(precision: StatusMetric["precision"]): HTMLElement {
  return badge(precision === "exact" ? "Exact" : "Estimated", precision);
}

function span(dataset: StatusDataset): HTMLElement {
  const wrapper = element("span", "gw-status-span");
  if (dataset.valid_from === null && dataset.valid_to === null) {
    wrapper.append(textValue("Not served"));
    return wrapper;
  }
  wrapper.append(
    timeOrFallback(dataset.valid_from, "Not served"),
    textValue(" – "),
    timeOrFallback(dataset.valid_to, "Not served"),
  );
  return wrapper;
}

/** The dataset's served caveat and count time, one click from the number they qualify. */
function datasetNote(dataset: StatusDataset): HTMLElement {
  const note = element("details", "gw-status-note gw-status-row-note");
  const summary = document.createElement("summary");
  summary.textContent = "What this counts";
  summary.setAttribute("data-no-glossary", "");
  const detail = document.createElement("p");
  detail.textContent = dataset.detail;
  const counted = element("p", "gw-status-card-time");
  counted.append("Counted ", timeOrFallback(dataset.counted_at, "not recorded"));
  note.append(summary, detail, counted);
  return note;
}

function jobs(payload: StatusPayload): HTMLElement {
  const section = sectionWithTitle("gw-status-jobs-title", "Scheduled work", NOTES.jobs);
  const wrapper = element("div", "gw-status-table-wrap");
  const table = document.createElement("table");
  table.className = "gw-status-table";
  const caption = document.createElement("caption");
  caption.textContent = "Registered timers and the runs the platform persisted";
  const head = tableHead(["Job", "State", "Timer", "Last run", "Next run", "Detail"]);
  const body = document.createElement("tbody");
  for (const job of payload.jobs) {
    const row = document.createElement("tr");
    const name = document.createElement("th");
    name.scope = "row";
    name.textContent = job.label;
    const state = effectiveState(job.state, payload.snapshot_state);
    row.append(
      name,
      tableCell(badge(STATE_LABELS[state], state)),
      tableCell(timer(job)),
      tableCell(timeOrFallback(job.last_run_at, "Not recorded")),
      tableCell(timeOrFallback(job.next_run_at, "Not recorded")),
      tableCell(textValue(job.detail)),
    );
    body.append(row);
  }
  if (payload.jobs.length === 0) body.append(emptyTableRow(6, "No job observations were served."));
  table.append(caption, head, body);
  wrapper.append(table);
  section.append(wrapper);
  return section;
}

function timer(job: StatusJob): HTMLElement {
  const wrapper = element("span", "gw-status-timer");
  if (job.unit === null) {
    wrapper.append(textValue("Not registered"));
    return wrapper;
  }
  wrapper.append(textValue(job.unit, true));
  wrapper.append(
    job.timer_armed === null
      ? badge("Evidence unavailable", "unavailable")
      : badge(job.timer_armed ? "Armed" : "Not armed", job.timer_armed ? "ok" : "degraded"),
  );
  return wrapper;
}

function sources(items: StatusSource[]): HTMLElement {
  const section = sectionWithTitle(
    "gw-status-sources-title",
    "Source polls & freshness",
    NOTES.sources,
  );
  const wrapper = element("div", "gw-status-table-wrap");
  const table = document.createElement("table");
  table.className = "gw-status-table gw-status-source-table";
  const caption = document.createElement("caption");
  caption.textContent = "Durable source polls and registered artifact freshness";
  const head = tableHead([
    "Source",
    "State",
    "Last attempt",
    "Outcome",
    "Next expected",
    "Cadence",
    { label: "Artifact retrieved", term: "gt_retrieval_vintage" },
    "Declared vintage",
    { label: "Latest artifact", term: "gt_manifest" },
    "Artifacts",
    "Reason",
  ]);
  const body = document.createElement("tbody");
  for (const source of items) {
    const row = document.createElement("tr");
    const name = document.createElement("th");
    name.scope = "row";
    name.append(document.createTextNode(source.name));
    const id = document.createElement("code");
    id.textContent = source.source_id;
    name.append(id);
    const outcome =
      source.last_outcome === null
        ? textValue("Not recorded")
        : badge(OUTCOME_LABELS[source.last_outcome], source.last_outcome);
    row.append(
      name,
      tableCell(badge(STATE_LABELS[source.state], source.state)),
      tableCell(timeOrFallback(source.last_attempt_at, "Never")),
      tableCell(outcome),
      tableCell(timeOrFallback(source.next_expected_poll, "Not predictable")),
      tableCell(textValue(source.cadence ?? "Not registered")),
      tableCell(timeOrFallback(source.retrieval_vintage, "Never")),
      tableCell(timeOrFallback(source.declared_vintage, "Not declared")),
      tableCell(textValue(source.last_manifest_id ?? "None", source.last_manifest_id !== null)),
      tableCell(countedValue(source.manifest_count, "artifacts", MANIFEST_COUNT_REASON)),
      tableCell(textValue(source.freshness_reason)),
    );
    body.append(row);
  }
  if (items.length === 0) body.append(emptyTableRow(11, "No registered sources were served."));
  table.append(caption, head, body);
  wrapper.append(table);
  section.append(wrapper);
  return section;
}

function disclosures(items: StatusPayload["disclosures"]): HTMLElement {
  const section = sectionWithTitle(
    "gw-status-disclosures-title",
    "Observability boundaries",
    NOTES.disclosures,
  );
  const list = element("ul", "gw-status-disclosures");
  for (const disclosure of items) {
    const item = document.createElement("li");
    const head = element("div", "gw-status-card-head");
    const title = document.createElement("h3");
    title.textContent = disclosure.label;
    head.append(
      title,
      badge(
        disclosure.state === "limited" ? "Limited" : "Not instrumented",
        disclosure.state,
      ),
    );
    const detail = document.createElement("p");
    detail.textContent = disclosure.detail;
    item.append(head, detail);
    list.append(item);
  }
  if (items.length === 0) list.append(emptyListItem("No observability disclosures were served."));
  section.append(list);
  return section;
}

function sectionWithTitle(
  id: string,
  titleText: string,
  note: { summary: string; text: string },
): HTMLElement {
  const section = element("section", "gw-status-section");
  section.setAttribute("aria-labelledby", id);
  const head = element("div", "gw-status-section-head");
  const title = element("h2", "gw-status-section-title");
  title.id = id;
  title.textContent = titleText;
  head.append(title, sectionNote(note));
  section.append(head);
  return section;
}

function sectionNote(note: { summary: string; text: string }): HTMLElement {
  const disclosure = element("details", "gw-status-note");
  const summary = document.createElement("summary");
  summary.textContent = note.summary;
  summary.setAttribute("data-no-glossary", "");
  const body = document.createElement("p");
  body.textContent = note.text;
  disclosure.append(summary, body);
  return disclosure;
}

/** Anonymous reads on is the alarming state, so the colour follows the risk, not the flag. */
function anonymousValue(enabled: boolean): HTMLElement {
  return badge(enabled ? "Enabled" : "Disabled", enabled ? "degraded" : "ok");
}

function servedValue(served: boolean): HTMLElement {
  return badge(served ? "Served" : "Not served", served ? "ok" : "unavailable");
}

function snapshotMessage(state: SnapshotState): string {
  if (state === "current") return "This snapshot is current according to the serving contract.";
  if (state === "stale") {
    return "The snapshot is stale. Previously successful checks are shown as unavailable, never as current green infrastructure.";
  }
  if (state === "unavailable") {
    return "The collector has no usable current snapshot. Successful-looking check values are suppressed.";
  }
  return "The collector marked this snapshot invalid. Successful-looking check values are suppressed.";
}

function effectiveState(state: CheckState, snapshot: SnapshotState): CheckState {
  return snapshot === "current" || state !== "ok" ? state : "unavailable";
}

function badge(label: string, state: string): HTMLElement {
  const value = element("span", "gw-status-badge");
  value.dataset["state"] = state;
  // A state, not vocabulary — and the pill is inline-flex, so a term splitting "Current
  // snapshot" in two would drop the space between the halves.
  value.setAttribute("data-no-glossary", "");
  value.textContent = label;
  return value;
}

function fact(list: HTMLDListElement | HTMLElement, label: string, value: Node): void {
  const term = document.createElement("dt");
  term.textContent = label;
  const detail = document.createElement("dd");
  detail.append(value);
  list.append(term, detail);
}

function summaryFact(list: HTMLElement, label: string, value: Node): void {
  const group = element("div", "gw-status-fact");
  fact(group, label, value);
  list.append(group);
}

function countedValue(value: number, unit: string, reason: string): HTMLElement {
  const wrapper = element("span", "gw-status-count");
  const count = document.createElement("gw-count");
  count.setAttribute("value", String(value));
  count.setAttribute("reason", reason);
  const suffix = element("span", "gw-status-unit");
  suffix.textContent = unit;
  wrapper.append(count, suffix);
  return wrapper;
}

function textValue(value: string, code = false): HTMLElement {
  const output = document.createElement(code ? "code" : "span");
  output.textContent = value;
  return output;
}

function timeOrFallback(value: string | null, fallback: string): HTMLElement {
  if (value === null) return textValue(fallback);
  const time = document.createElement("time");
  time.dateTime = value;
  time.textContent = displayTime(value);
  return time;
}

/** Exported beside `element`, so the Accounts tables stamp a time the way this page does. */
export function displayTime(value: string): string {
  if (/^\d{4}-\d{2}(-\d{2})?$/.test(value)) return value;
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) return value;
  return parsed.toISOString().replace("T", " ").replace(/:\d{2}\.\d{3}Z$/, " UTC");
}

/** A column head is prose unless its wording is the product's name for something else. */
type Column = string | { label: string; term: string };

function tableHead(columns: readonly Column[]): HTMLTableSectionElement {
  const head = document.createElement("thead");
  const row = document.createElement("tr");
  for (const column of columns) {
    const cell = document.createElement("th");
    cell.scope = "col";
    if (typeof column === "string") cell.textContent = column;
    else cell.append(labelElement(column.label, column.term));
    row.append(cell);
  }
  head.append(row);
  return head;
}

function tableCell(value: Node): HTMLTableCellElement {
  const cell = document.createElement("td");
  cell.append(value);
  return cell;
}

function emptyTableRow(columns: number, message: string): HTMLTableRowElement {
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = columns;
  cell.className = "gw-status-empty";
  cell.textContent = message;
  row.append(cell);
  return row;
}

function emptyListItem(message: string): HTMLLIElement {
  const item = document.createElement("li");
  item.className = "gw-status-empty";
  item.textContent = message;
  return item;
}

function emptyBlock(message: string): HTMLElement {
  const item = element("p", "gw-status-empty");
  item.textContent = message;
  return item;
}

/** Exported for `accounts/`, which mounts inside this surface: three private copies of this
 * helper already exist in the tree and a fourth would be one more than the tree needs. */
export function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className: string,
): HTMLElementTagNameMap[K] {
  const created = document.createElement(tag);
  created.className = className;
  return created;
}

function aborted(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

class StatusContractError extends Error {
  constructor(path: string, expected: string) {
    super(`The server returned an invalid status payload: ${path} must be ${expected}.`);
    this.name = "StatusContractError";
  }
}

function statusPayload(value: unknown): StatusPayload {
  const root = record(value, "data");
  return {
    observed_at: nullableTime(root["observed_at"], "data.observed_at"),
    snapshot_state: member(
      root["snapshot_state"],
      "data.snapshot_state",
      ["current", "stale", "unavailable", "invalid"] as const,
    ),
    state: member(root["state"], "data.state", ["ok", "degraded", "partial"] as const),
    checks: array(root["checks"], "data.checks").map((item, index) => {
      const check = record(item, `data.checks[${index}]`);
      return {
        id: string(check["id"], `data.checks[${index}].id`),
        label: string(check["label"], `data.checks[${index}].label`),
        state: member(
          check["state"],
          `data.checks[${index}].state`,
          ["ok", "degraded", "pending", "unavailable", "not_instrumented"] as const,
        ),
        observed_at: nullableTime(check["observed_at"], `data.checks[${index}].observed_at`),
        detail: string(check["detail"], `data.checks[${index}].detail`),
        tier: nullableMember(
          check["tier"] ?? null,
          `data.checks[${index}].tier`,
          ["serving", "data", "edge", "host"] as const,
        ),
        probe: nullableString(check["probe"] ?? null, `data.checks[${index}].probe`),
      };
    }),
    datasets: array(root["datasets"], "data.datasets").map(datasetOf),
    jobs: array(root["jobs"], "data.jobs").map(jobOf),
    sources: array(root["sources"], "data.sources").map(sourceOf),
    platform: platformOf(root["platform"]),
    deployment: deploymentOf(root["deployment"]),
    disclosures: array(root["disclosures"], "data.disclosures").map((item, index) => {
      const disclosure = record(item, `data.disclosures[${index}]`);
      return {
        id: string(disclosure["id"], `data.disclosures[${index}].id`),
        label: string(disclosure["label"], `data.disclosures[${index}].label`),
        state: member(
          disclosure["state"],
          `data.disclosures[${index}].state`,
          ["not_instrumented", "limited"] as const,
        ),
        detail: string(disclosure["detail"], `data.disclosures[${index}].detail`),
      };
    }),
  };
}

function datasetOf(item: unknown, index: number): StatusDataset {
  const path = `data.datasets[${index}]`;
  const dataset = record(item, path);
  return {
    dataset_id: string(dataset["dataset_id"], `${path}.dataset_id`),
    label: string(dataset["label"], `${path}.label`),
    scope: string(dataset["scope"], `${path}.scope`),
    grain: string(dataset["grain"], `${path}.grain`),
    state: member(dataset["state"], `${path}.state`, ["available", "unavailable"] as const),
    counted_at: nullableTime(dataset["counted_at"], `${path}.counted_at`),
    latest_knowledge_at: nullableTime(
      dataset["latest_knowledge_at"],
      `${path}.latest_knowledge_at`,
    ),
    metrics: array(dataset["metrics"], `${path}.metrics`).map((item_, metricIndex) => {
      const metricPath = `${path}.metrics[${metricIndex}]`;
      const metric = record(item_, metricPath);
      return {
        metric_id: string(metric["metric_id"], `${metricPath}.metric_id`),
        label: string(metric["label"], `${metricPath}.label`),
        value: countNumber(metric["value"], `${metricPath}.value`),
        unit: string(metric["unit"], `${metricPath}.unit`),
        precision: member(metric["precision"], `${metricPath}.precision`, ["exact", "estimated"] as const),
        reason: nonEmptyString(metric["reason"], `${metricPath}.reason`),
      };
    }),
    valid_from: nullableTime(dataset["valid_from"], `${path}.valid_from`),
    valid_to: nullableTime(dataset["valid_to"], `${path}.valid_to`),
    detail: string(dataset["detail"], `${path}.detail`),
  };
}

function jobOf(item: unknown, index: number): StatusJob {
  const path = `data.jobs[${index}]`;
  const job = record(item, path);
  return {
    id: string(job["id"], `${path}.id`),
    label: string(job["label"], `${path}.label`),
    state: member(
      job["state"],
      `${path}.state`,
      ["ok", "degraded", "pending", "unavailable", "not_instrumented"] as const,
    ),
    last_run_at: nullableTime(job["last_run_at"], `${path}.last_run_at`),
    next_run_at: nullableTime(job["next_run_at"], `${path}.next_run_at`),
    detail: string(job["detail"], `${path}.detail`),
    unit: nullableString(job["unit"] ?? null, `${path}.unit`),
    timer_armed: nullableBoolean(job["timer_armed"] ?? null, `${path}.timer_armed`),
  };
}

function sourceOf(item: unknown, index: number): StatusSource {
  const path = `data.sources[${index}]`;
  const source = record(item, path);
  return {
    source_id: string(source["source_id"], `${path}.source_id`),
    name: string(source["name"], `${path}.name`),
    state: member(source["state"], `${path}.state`, ["current", "stale", "pending"] as const),
    retrieval_vintage: nullableTime(source["retrieval_vintage"], `${path}.retrieval_vintage`),
    declared_vintage: nullableTime(source["declared_vintage"], `${path}.declared_vintage`),
    last_manifest_id: nullableString(source["last_manifest_id"], `${path}.last_manifest_id`),
    manifest_count: countNumber(source["manifest_count"], `${path}.manifest_count`),
    last_attempt_at: nullableTime(source["last_attempt_at"], `${path}.last_attempt_at`),
    last_outcome: nullableMember(
      source["last_outcome"],
      `${path}.last_outcome`,
      ["attempted", "new", "unchanged", "failed", "interrupted"] as const,
    ),
    next_expected_poll: nullableTime(
      source["next_expected_poll"],
      `${path}.next_expected_poll`,
    ),
    cadence: nullableBoundedString(source["cadence"], `${path}.cadence`, 80),
    freshness_reason: boundedString(source["freshness_reason"], `${path}.freshness_reason`, 512),
  };
}

function platformOf(item: unknown): StatusPayload["platform"] {
  const platform = record(item, "data.platform");
  return {
    code_version: nullableString(platform["code_version"], "data.platform.code_version"),
    schema_version: nullableCount(platform["schema_version"], "data.platform.schema_version"),
    schema_version_reason: nonEmptyString(
      platform["schema_version_reason"],
      "data.platform.schema_version_reason",
    ),
    database_bytes: nullableCount(platform["database_bytes"], "data.platform.database_bytes"),
    database_bytes_reason: nonEmptyString(
      platform["database_bytes_reason"],
      "data.platform.database_bytes_reason",
    ),
    edge_host: nullableString(platform["edge_host"] ?? null, "data.platform.edge_host"),
  };
}

/** Absent on a server older than this surface; the page says "not served" rather than guessing. */
function deploymentOf(item: unknown): StatusPayload["deployment"] {
  if (item === undefined || item === null) return null;
  const posture = record(item, "data.deployment");
  return {
    public_origin: boolean(posture["public_origin"], "data.deployment.public_origin"),
    anonymous_reads: boolean(posture["anonymous_reads"], "data.deployment.anonymous_reads"),
    spa_served: boolean(posture["spa_served"], "data.deployment.spa_served"),
    basemap_served: boolean(posture["basemap_served"], "data.deployment.basemap_served"),
    tile_upstream: member(posture["tile_upstream"], "data.deployment.tile_upstream", [
      "default",
      "configured",
    ] as const),
    csp_report_only: boolean(posture["csp_report_only"], "data.deployment.csp_report_only"),
  };
}

function record(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new StatusContractError(path, "an object");
  }
  return value as Record<string, unknown>;
}

function array(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) throw new StatusContractError(path, "an array");
  return value;
}

function string(value: unknown, path: string): string {
  if (typeof value !== "string") throw new StatusContractError(path, "a string");
  return value;
}

function nullableString(value: unknown, path: string): string | null {
  if (value === null) return null;
  return string(value, path);
}

function boolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") throw new StatusContractError(path, "a boolean");
  return value;
}

function nullableBoolean(value: unknown, path: string): boolean | null {
  if (value === null) return null;
  return boolean(value, path);
}

function nullableBoundedString(value: unknown, path: string, maximum: number): string | null {
  if (value === null) return null;
  return boundedString(value, path, maximum);
}

function nullableTime(value: unknown, path: string): string | null {
  const text = nullableString(value, path);
  if (text === null) return null;
  if (/^\d{4}-\d{2}$/.test(text)) {
    const month = Number(text.slice(5));
    if (month >= 1 && month <= 12) return text;
  } else if (/^\d{4}-\d{2}-\d{2}$/.test(text) && validIsoDate(text)) {
    return text;
  } else if (
    /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.test(
      text,
    ) &&
    validIsoDate(text.slice(0, 10)) &&
    Number.isFinite(Date.parse(text))
  ) {
    return text;
  }
  throw new StatusContractError(path, "an ISO month, date, or timestamp");
}

function validIsoDate(value: string): boolean {
  const parsed = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value;
}

function focusRefresh(mount: Mount): void {
  mount.host.querySelector<HTMLButtonElement>(".gw-status-refresh")?.focus();
}

function nonEmptyString(value: unknown, path: string): string {
  const found = string(value, path);
  if (found.trim() === "") throw new StatusContractError(path, "a non-empty string");
  return found;
}

function boundedString(value: unknown, path: string, maximum: number): string {
  const found = nonEmptyString(value, path);
  if (found.length > maximum) {
    throw new StatusContractError(path, `a non-empty string of at most ${maximum} characters`);
  }
  return found;
}

function countNumber(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new StatusContractError(path, "a safe non-negative integer");
  }
  return value;
}

function nullableCount(value: unknown, path: string): number | null {
  if (value === null) return null;
  return countNumber(value, path);
}

function member<const T extends readonly string[]>(value: unknown, path: string, members: T): T[number] {
  if (typeof value !== "string" || !(members as readonly string[]).includes(value)) {
    throw new StatusContractError(path, `one of ${members.join(", ")}`);
  }
  return value as T[number];
}

function nullableMember<const T extends readonly string[]>(
  value: unknown,
  path: string,
  members: T,
): T[number] | null {
  if (value === null) return null;
  return member(value, path, members);
}
