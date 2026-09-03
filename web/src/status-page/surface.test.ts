// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client.ts";
import { clearSession, seedSession } from "../test/session.ts";
import { mountStatusPage, unmountStatusPage } from "./surface.ts";
import type { StatusPayload } from "./surface.ts";

const METRIC_REASON =
  "A physical row count is operational inventory at the named grain, not a petroleum measurement.";
const STORAGE_REASON =
  "Database bytes are an operational storage reading, not a petroleum measurement.";

const PAYLOAD: StatusPayload = {
  observed_at: "2026-08-26T18:00:00Z",
  snapshot_state: "current",
  state: "partial",
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
    {
      id: "tunnel",
      label: "Cloudflare tunnel",
      state: "degraded",
      observed_at: "2026-08-26T18:00:00Z",
      detail: "Service manager does not report active.",
      tier: "edge",
      probe: "cloudflared.service",
    },
    {
      id: "backup",
      label: "Remote backup",
      state: "not_instrumented",
      observed_at: null,
      detail: "No persisted remote-copy result exists.",
      tier: null,
      probe: null,
    },
  ],
  datasets: [
    {
      dataset_id: "canonical.production_monthly/nd",
      label: "North Dakota production observations",
      scope: "North Dakota",
      grain: "well-month-stream observation",
      state: "available",
      counted_at: "2026-08-26T17:45:00Z",
      latest_knowledge_at: "2026-08-26T17:30:00Z",
      metrics: [
        {
          metric_id: "rows",
          label: "Physical rows",
          value: 7_223_544,
          unit: "rows",
          precision: "estimated",
          reason: METRIC_REASON,
        },
        {
          metric_id: "months",
          label: "Distinct months",
          value: 131,
          unit: "months",
          precision: "exact",
          reason: METRIC_REASON,
        },
      ],
      valid_from: "2015-05",
      valid_to: "2026-03",
      detail: "Append-only source observations; not a count of unique wells.",
    },
    {
      dataset_id: "lineage.conformance_rules",
      label: "Registered conformance rules",
      scope: "All registered sources",
      grain: "one registered mapping decision per rule id",
      state: "available",
      counted_at: "2026-08-26T17:45:00Z",
      latest_knowledge_at: null,
      metrics: [
        {
          metric_id: "rules",
          label: "Registered rules",
          value: 431,
          unit: "rules",
          precision: "exact",
          reason: METRIC_REASON,
        },
      ],
      valid_from: null,
      valid_to: null,
      detail: "A mapping that exists only in code is not counted here.",
    },
  ],
  jobs: [
    {
      id: "ingest_nd_gis",
      label: "North Dakota GIS ingest",
      state: "pending",
      last_run_at: "2026-08-26T04:30:00Z",
      next_run_at: null,
      detail: "Next-run time is not persisted.",
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
      id: "ingest_fracfocus",
      label: "FracFocus archive ingest",
      state: "ok",
      last_run_at: "2026-07-01T02:00:00Z",
      next_run_at: null,
      // The row the v0.78 visual gate measured N2, N3 and N6 on: `detail` falls back to the
      // cadence note when a job records no refusal, the note carries a command-line flag, and
      // its next-due instant is a month behind the observation.
      detail: "Owner-triggered; the release takes the archive with --promote-design",
      unit: null,
      timer_armed: null,
      kind: "ingest",
      jurisdiction: null,
      cadence: "Owner-triggered; the release takes the archive with --promote-design",
      next_due_at: "2026-08-05T03:00:00Z",
      duration_seconds: null,
      last_outcome: "refused",
      refusal_code: null,
      refusal_class: null,
      launch_mode: "observe",
      schedule: {
        job_id: "ingest_fracfocus",
        effective_from: "2026-09-02",
        published_at: "2026-09-02",
        rule_id: "cr_job_cadence_ingest_fracfocus_1",
        rationale: "The archive is republished without notice, so the release decides when.",
        external_timer_unit: null,
        external_service_unit: null,
      },
    },
    {
      id: "recovery_drill",
      label: "Replacement-host recovery",
      state: "pending",
      last_run_at: null,
      next_run_at: null,
      detail: "No recovery has been proven.",
      unit: null,
      timer_armed: null,
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
      source_id: "nd_mpr_xlsx",
      name: "North Dakota monthly production",
      state: "current",
      retrieval_vintage: "2026-08-05",
      declared_vintage: "2026-05-01",
      last_manifest_id: "mf_nd_01",
      manifest_count: 18,
      last_attempt_at: "2026-08-26T17:55:00Z",
      last_outcome: "unchanged",
      next_expected_poll: "2026-09-03T17:56:00Z",
      cadence: "Every 8 days",
      freshness_reason:
        "The latest poll completed unchanged inside cadence; the older artifact remains current because its bytes were rechecked successfully.",
    },
    {
      source_id: "tx_completion",
      name: "Texas completion data",
      state: "pending",
      retrieval_vintage: null,
      declared_vintage: null,
      last_manifest_id: null,
      manifest_count: 0,
      last_attempt_at: null,
      last_outcome: null,
      next_expected_poll: null,
      cadence: "Every 35 days",
      freshness_reason: "No durable poll attempt or registered artifact exists yet.",
    },
  ],
  platform: {
    code_version: "v0.55+abcdef0",
    schema_version: 44,
    schema_version_reason:
      "Schema migration sequence is deployment bookkeeping, not a petroleum measurement.",
    database_bytes: 12_345_678,
    database_bytes_reason: STORAGE_REASON,
    edge_host: "glasswell.rpx.sh",
  },
  deployment: {
    public_origin: true,
    anonymous_reads: false,
    spa_served: true,
    basemap_served: false,
    tile_upstream: "default",
    csp_report_only: false,
  },
  disclosures: [
    {
      id: "restore-drill",
      label: "Restore drill",
      state: "not_instrumented",
      detail: "No persisted execution result is available.",
    },
  ],
};

const onForbidden = vi.fn();
let host: HTMLElement;

function envelope(data: unknown): Response {
  return new Response(JSON.stringify({ data, meta: {}, links: {} }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function problem(status: number, title: string, requestId?: string): Response {
  return new Response(
    JSON.stringify({
      type: status === 403 ? "https://glasswell.local/problems/key_rejected" : "about:blank",
      title,
      status,
      request_id: requestId,
    }),
    {
      status,
      statusText: title,
      headers: { "content-type": "application/problem+json" },
    },
  );
}

beforeEach(() => {
  document.body.innerHTML = '<div id="gw-status-page"></div>';
  host = document.getElementById("gw-status-page") as HTMLElement;
  onForbidden.mockClear();
  seedSession();
});

afterEach(() => {
  unmountStatusPage();
  vi.unstubAllGlobals();
  clearSession();
});

describe("the job tables answer with what a reader does not already have", () => {
  // gate-v078 N2/N3/N6, on the register. Rendered from PAYLOAD directly rather than through a
  // mounted page, so each case names one cell rather than the whole surface.
  const rowFor = (label: string): HTMLElement => {
    const rows = [...host.querySelectorAll("tbody tr")] as HTMLElement[];
    const row = rows.find((item) => item.querySelector("th")?.textContent?.startsWith(label));
    expect(row, `no job row for ${label}`).toBeTruthy();
    return row as HTMLElement;
  };

  beforeEach(async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(envelope(PAYLOAD)));
    await mountStatusPage(host, { onForbidden });
  });

  it("N2: does not open the disclosure on the sentence already in the Cadence cell", () => {
    const repeated = rowFor("FracFocus archive ingest");
    const cadence = repeated.querySelectorAll("td")[1]?.textContent?.trim();
    const paragraphs = [...repeated.querySelectorAll("details p")].map((node) =>
      node.textContent?.trim(),
    );

    expect(cadence).toContain("Owner-triggered");
    expect(paragraphs).not.toContain(cadence);
    expect(paragraphs.length).toBeGreaterThan(0);
    // The row whose detail says something the Cadence cell does not still says it.
    const distinct = rowFor("North Dakota GIS ingest");
    expect([...distinct.querySelectorAll("details p")].map((node) => node.textContent)).toContain(
      PAYLOAD.jobs[0]?.detail,
    );
  });

  it("N3: holds a command-line flag on one line, still spelled with ASCII hyphens", () => {
    const row = rowFor("FracFocus archive ingest");
    const held = row.querySelector(".gw-nowrap");

    expect(held?.textContent).toBe("--promote-design");
    expect(row.querySelectorAll("td")[1]?.textContent).toContain("--promote-design");
  });

  it("N6: says a next-due instant that has already passed was due, not is due", () => {
    const overdue = rowFor("FracFocus archive ingest").querySelector(".gw-status-overdue");
    const ahead = rowFor("North Dakota GIS ingest").querySelector(".gw-status-overdue");

    expect(overdue?.textContent).toContain("Was due");
    expect(ahead).toBeNull();
  });
});

describe("the job fixtures carry a shape the collector could emit", () => {
  // The collector builds `id`, `schedule.job_id` and `schedule.rule_id` from one registry row,
  // so a fixture where they disagree pins a payload no producer can send. A green suite over
  // one of those is the class of fixture that once kept CI green across a real break.
  it("names one job in the id, the schedule and the rule it cites", () => {
    for (const job of PAYLOAD.jobs) {
      if (job.schedule === null) continue;
      expect(job.schedule.job_id).toBe(job.id);
      if (job.schedule.rule_id === null) continue;
      expect(job.schedule.rule_id).toMatch(new RegExp(`^cr_job_cadence_${job.id}_\\d+$`));
    }
  });
});

describe("the Status surface", () => {
  it("shows an announced loading state before the request resolves", async () => {
    let resolveResponse: ((response: Response) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      () => new Promise<Response>((resolve) => (resolveResponse = resolve)),
    );

    const pending = mountStatusPage(host, { onForbidden });

    expect(host.getAttribute("aria-busy")).toBe("true");
    expect(host.querySelector('[role="status"]')?.textContent).toContain("Checking infrastructure");

    resolveResponse?.(envelope(PAYLOAD));
    await pending;
    expect(host.getAttribute("aria-busy")).toBe("false");
  });

  it("renders semantic checks, inventory, jobs, source age, times, and disclosures", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(envelope(PAYLOAD)));

    await mountStatusPage(host, { onForbidden });

    expect(host.querySelector("h1")?.textContent).toBe("Status");
    expect([...host.querySelectorAll("section h2")].map((heading) => heading.textContent)).toEqual([
      "Deployment",
      "Architecture",
      "Data footprint",
      "Scheduled work",
      "Source polls & freshness",
      "Observability boundaries",
    ]);
    expect(host.querySelectorAll("dl").length).toBeGreaterThan(0);
    // Five: checks, datasets, two grouped data-job tables — one jurisdiction, one
    // cross-jurisdiction — and the platform-job table.
    expect(host.querySelectorAll("table")).toHaveLength(5);
    expect(host.querySelectorAll("time").length).toBeGreaterThan(4);
    expect(host.textContent).toContain("Unchanged");
    expect(host.textContent).toContain("Every 8 days");
    expect(host.textContent).toContain("2026-09-03 17:56 UTC");
    expect(host.textContent).toContain("2026-05-01");
    expect(host.textContent).toContain("mf_nd_01");
    expect(host.textContent).toContain("well-month-stream observation");
    expect(host.textContent).toContain("Latest knowledge");
    expect(
      [...host.querySelectorAll("time")].some(
        (time) => time.getAttribute("datetime") === "2026-08-26T17:30:00Z",
      ),
    ).toBe(true);
    expect(host.textContent).toContain("Not instrumented");
  });

  it("states the deployment identity and the posture the serving process enforces", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(envelope(PAYLOAD)));

    await mountStatusPage(host, { onForbidden });

    const facts = host.querySelector(".gw-status-facts") as HTMLElement;
    const labels = [...facts.querySelectorAll("dt")].map((term) => term.textContent);
    expect(labels).toEqual([
      "Code version",
      "Schema head",
      "Edge host",
      "Observed",
      "Database storage",
      "Origin",
      "Anonymous reads",
      "Tile upstream",
      "Frontend bundle",
      "Local basemap",
      "CSP",
    ]);
    expect(facts.textContent).toContain("glasswell.rpx.sh");
    expect(facts.textContent).toContain("Public");
    expect(facts.textContent).toContain("Disabled");
    expect(facts.textContent).toContain("Enforced");
    expect(facts.textContent).toContain("Default");
  });

  it("says not served for a posture an older server does not carry", async () => {
    const { deployment: _omitted, ...withoutPosture } = PAYLOAD;
    vi.stubGlobal("fetch", () => Promise.resolve(envelope(withoutPosture)));

    await mountStatusPage(host, { onForbidden });

    const facts = host.querySelector(".gw-status-facts") as HTMLElement;
    expect(facts.textContent).not.toContain("Public");
    expect([...facts.querySelectorAll("dd")].filter((cell) => cell.textContent === "Not served")).toHaveLength(6);
  });

  it("groups components by tier and names the probe each one was observed through", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(envelope(PAYLOAD)));

    await mountStatusPage(host, { onForbidden });

    const section = host.querySelector("#gw-status-checks-title")?.closest("section") as HTMLElement;
    expect([...section.querySelectorAll(".gw-status-tier")].map((tier) => tier.textContent)).toEqual([
      "Serving plane",
      "Edge",
      "Unclassified",
    ]);
    expect(section.textContent).toContain("cloudflared.service");
    expect(section.textContent).toContain("No probe registered");
    expect(section.querySelector('[data-state="degraded"]')?.textContent).toBe("Degraded");
  });

  it("reports each timer's unit and whether it is armed, without inferring a run from it", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(envelope(PAYLOAD)));

    await mountStatusPage(host, { onForbidden });

    const jobs = host.querySelector("#gw-status-jobs-title")?.closest("section") as HTMLElement;
    expect(jobs.textContent).toContain("glasswell-ingest.timer");
    expect(jobs.textContent).toContain("Armed");
    expect(jobs.textContent).toContain("Not registered");
    const armed = jobs.querySelector(".gw-status-timer") as HTMLElement;
    expect(armed.querySelector(".gw-status-badge")?.textContent).toBe("Armed");
    // Armed is a schedule fact; the run beside it is still Pending.
    expect(armed.closest("tr")?.querySelector('[data-state="pending"]')).not.toBeNull();
  });

  it("groups the footprint by storage layer and keeps every magnitude on its own grain", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(envelope(PAYLOAD)));

    await mountStatusPage(host, { onForbidden });

    const table = host.querySelector(".gw-status-footprint") as HTMLElement;
    expect([...table.querySelectorAll(".gw-status-layer-row code")].map((code) => code.textContent)).toEqual([
      "canonical",
      "lineage",
    ]);
    expect(table.textContent).toContain("canonical.production_monthly/nd");
    expect(table.textContent).toContain("2015-05");
    expect(table.textContent).toContain("2026-03");
    expect(table.textContent).toContain("131");
    // No headline total: unrelated populations are never summed into one records number.
    expect(table.textContent).not.toContain("Total records");
  });

  it("marks precision once per row when uniform and per metric when it is mixed", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(envelope(PAYLOAD)));

    await mountStatusPage(host, { onForbidden });

    const rows = [...host.querySelectorAll(".gw-status-footprint tbody tr")];
    const mixed = rows.find((row) => row.textContent?.includes("production_monthly")) as HTMLElement;
    const uniform = rows.find((row) => row.textContent?.includes("conformance_rules")) as HTMLElement;
    expect(
      [...mixed.querySelectorAll(".gw-status-magnitudes .gw-status-badge")].map((one) => one.textContent),
    ).toEqual(["Estimated", "Exact"]);
    expect(uniform.querySelectorAll(".gw-status-magnitudes .gw-status-badge")).toHaveLength(0);
    expect(uniform.querySelector("td .gw-status-badge")?.textContent).toBe("Exact");
  });

  it("keeps every method caveat reachable behind a closed disclosure rather than above the facts", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(envelope(PAYLOAD)));

    await mountStatusPage(host, { onForbidden });

    const notes = [...host.querySelectorAll("details.gw-status-note")];
    expect(notes.length).toBeGreaterThanOrEqual(6);
    expect(notes.every((note) => !(note as HTMLDetailsElement).open)).toBe(true);
    expect(notes.map((note) => note.querySelector("summary")?.textContent)).toContain(
      "How freshness is decided",
    );
    expect(host.textContent).toContain("failed or interrupted checks cannot");
    expect(host.textContent).toContain("A successful check proves only the detail it names");
    expect(host.textContent).toContain("Unrelated row populations are never summed");
    expect(host.textContent).toContain("an installed timer is not treated as proof");
    // The caveat lives inside the disclosure, never as a standing paragraph beside the heading.
    expect(
      [...host.querySelectorAll("section > p, .gw-status-section-head > p")].map((one) => one.textContent),
    ).toEqual([]);
  });

  it("renders served operational reasons through gw-count", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(envelope(PAYLOAD)));

    await mountStatusPage(host, { onForbidden });

    // Derived, not pinned: every number the payload carries must reach the page wearing a
    // reason, so adding a served figure without a handle fails here.
    const served =
      2 + // schema head and database storage
      PAYLOAD.datasets.reduce((total, dataset) => total + dataset.metrics.length, 0) +
      PAYLOAD.sources.length; // one manifest count each
    const counts = [...host.querySelectorAll("gw-count")];
    expect(counts).toHaveLength(served);
    expect(counts.every((count) => (count.getAttribute("reason")?.length ?? 0) > 0)).toBe(true);
    expect(counts.map((count) => count.getAttribute("reason"))).toContain(STORAGE_REASON);
    expect(counts.map((count) => count.getAttribute("reason"))).toContain(METRIC_REASON);
    expect(host.querySelector('gw-count[value="12345678"]')?.textContent).toContain("12,345,678");
    expect(host.textContent).toContain("7,223,544");
    expect(host.textContent).toContain("44");
    expect(host.textContent).toContain("18");
    expect(host.textContent).toContain("Estimated");
  });

  it("never paints an old successful check as green when the snapshot is stale", async () => {
    vi.stubGlobal(
      "fetch",
      () => Promise.resolve(envelope({ ...PAYLOAD, snapshot_state: "stale", state: "degraded" })),
    );

    await mountStatusPage(host, { onForbidden });

    const summary = host.querySelector(".gw-status-summary") as HTMLElement;
    const check = host.querySelector(".gw-status-check") as HTMLElement;
    expect(summary.dataset["snapshot"]).toBe("stale");
    expect(summary.textContent).toContain("Previously successful checks are shown as unavailable");
    expect(check.querySelector('[data-state="ok"]')).toBeNull();
    expect(check.querySelector('[data-state="unavailable"]')?.textContent).toBe("Unavailable");
  });

  it("shows the problem and request ID, then retries through the same request path", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(problem(503, "Collector offline", "req_status_01"))
      .mockResolvedValueOnce(envelope(PAYLOAD));
    vi.stubGlobal("fetch", fetch);

    await mountStatusPage(host, { onForbidden });

    expect(host.textContent).toContain("Collector offline (HTTP 503)");
    expect(host.textContent).toContain("req_status_01");
    (host.querySelector(".gw-status-refresh") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(host.querySelector("h1")?.textContent).toBe("Status"));
    await vi.waitFor(() => expect(host.textContent).toContain("North Dakota production observations"));
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("rejects a malformed successful response instead of painting partial truth", async () => {
    vi.stubGlobal(
      "fetch",
      () =>
        Promise.resolve(
          envelope({
            ...PAYLOAD,
            datasets: [{ ...PAYLOAD.datasets[0], metrics: [{ ...PAYLOAD.datasets[0]?.metrics[0], value: "many" }] }],
          }),
        ),
    );

    await mountStatusPage(host, { onForbidden });

    expect(host.textContent).toContain("Status response is invalid");
    expect(host.textContent).toContain(
      "data.datasets[0].metrics[0].value must be a safe non-negative integer",
    );
    expect(host.textContent).not.toContain("Infrastructure checks");
  });

  it("rejects malformed observation time instead of labeling it as freshness", async () => {
    vi.stubGlobal("fetch", () =>
      Promise.resolve(envelope({ ...PAYLOAD, observed_at: "recently-ish" })),
    );

    await mountStatusPage(host, { onForbidden });

    expect(host.textContent).toContain("Status response is invalid");
    expect(host.textContent).toContain("data.observed_at must be an ISO month, date, or timestamp");
  });

  it.each(["August 26, 2026", "Wed, 26 Aug 2026 18:00:00 GMT", "2026-08-26T18:00:00"])(
    "rejects client-dependent time spelling %s",
    async (observedAt) => {
      vi.stubGlobal("fetch", () =>
        Promise.resolve(envelope({ ...PAYLOAD, observed_at: observedAt })),
      );

      await mountStatusPage(host, { onForbidden });

      expect(host.textContent).toContain("Status response is invalid");
    },
  );

  it("rejects negative, fractional, and unsafe operational counts", async () => {
    for (const value of [-1, 1.5, Number.MAX_SAFE_INTEGER + 1]) {
      vi.stubGlobal(
        "fetch",
        () =>
          Promise.resolve(
            envelope({
              ...PAYLOAD,
              sources: [{ ...PAYLOAD.sources[0], manifest_count: value }],
            }),
          ),
      );

      await mountStatusPage(host, { onForbidden });
      expect(host.textContent, String(value)).toContain("safe non-negative integer");
    }
  });

  it("bounds source reasons and renders them only as text", async () => {
    vi.stubGlobal(
      "fetch",
      () =>
        Promise.resolve(
          envelope({
            ...PAYLOAD,
            sources: [
              {
                ...PAYLOAD.sources[0],
                freshness_reason: '<img src=x onerror="window.compromised=true">',
              },
            ],
          }),
        ),
    );

    await mountStatusPage(host, { onForbidden });

    expect(host.querySelector("img")).toBeNull();
    expect(host.textContent).toContain('<img src=x onerror="window.compromised=true">');

    vi.stubGlobal("fetch", () =>
      Promise.resolve(
        envelope({
          ...PAYLOAD,
          sources: [{ ...PAYLOAD.sources[0], freshness_reason: "x".repeat(513) }],
        }),
      ),
    );
    await mountStatusPage(host, { onForbidden });
    expect(host.textContent).toContain("at most 512 characters");
  });

  it("labels malformed JSON as an invalid response", async () => {
    vi.stubGlobal(
      "fetch",
      () =>
        Promise.resolve(
          new Response("{not-json", {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        ),
    );

    await mountStatusPage(host, { onForbidden });

    expect(host.textContent).toContain("Status response is invalid");
    expect(host.querySelector(".gw-status-refresh")?.textContent).toBe("Retry");
  });

  it("routes a 403 to the owner-key hook and keeps an explicit retry state", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(problem(403, "Owner key rejected")));

    await mountStatusPage(host, { onForbidden });

    expect(onForbidden).toHaveBeenCalledOnce();
    expect(onForbidden.mock.calls[0]?.[0]).toBeInstanceOf(ApiError);
    expect(host.textContent).toContain("Status access required");
    expect(host.querySelector(".gw-status-refresh")?.textContent).toBe("Retry");
  });

  it("aborts an old mount and cannot let its late response overwrite the new host", async () => {
    let firstSignal: AbortSignal | undefined;
    let calls = 0;
    vi.stubGlobal("fetch", (_input: RequestInfo | URL, init?: RequestInit) => {
      calls += 1;
      if (calls === 1) {
        firstSignal = init?.signal ?? undefined;
        return new Promise<Response>((_resolve, reject) => {
          firstSignal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
        });
      }
      return Promise.resolve(envelope({ ...PAYLOAD, platform: { ...PAYLOAD.platform, code_version: "v0.55+new" } }));
    });

    const first = mountStatusPage(host, { onForbidden });
    const second = mountStatusPage(host, { onForbidden });
    await Promise.all([first, second]);

    expect(firstSignal?.aborted).toBe(true);
    expect(host.textContent).toContain("v0.55+new");
    expect(host.textContent).not.toContain("Status unavailable");
  });

  it("refreshes in place and replaces the observed snapshot", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(envelope(PAYLOAD))
      .mockResolvedValueOnce(envelope({ ...PAYLOAD, observed_at: "2026-08-26T19:00:00Z" }));
    vi.stubGlobal("fetch", fetch);

    await mountStatusPage(host, { onForbidden });
    const refresh = host.querySelector(".gw-status-refresh") as HTMLButtonElement;
    refresh.focus();
    refresh.click();

    await vi.waitFor(() =>
      expect(host.querySelector("time")?.getAttribute("datetime")).toBe("2026-08-26T19:00:00Z"),
    );
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(document.activeElement).toBe(host.querySelector(".gw-status-refresh"));
  });
});

describe("the deployment grid leaves its glossary rules somewhere to paint", () => {
  /**
   * gate-v075 defect 1, a major: `Schema head` and `Local basemap` are real gw-terms whose
   * dotted rule never painted at any width. A gw-term's `border-bottom` is a border on an
   * *inline* box, so it draws below the line box; with `padding-bottom: 0` on the dt it landed
   * outside the dt and under the opaque `background: var(--ink)` of the dd that follows it in
   * the flex column. Forcing a 3px solid red border did not paint either, which is what proved
   * over-paint rather than mis-specification.
   *
   * vitest loads no stylesheet, so this reads the shipped sheet — the idiom
   * map/layer-panel.test.ts uses. Both the base rule and the <=520px override are covered:
   * the narrow one is where it matters most, because there is no hover at 390.
   */
  it("never zeroes the dt padding a term's dotted rule needs", () => {
    const css = readFileSync("src/status-page/surface.css", "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    const owning = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
      .map((match) => ({ selector: (match[1] ?? "").trim(), body: match[2] ?? "" }))
      .filter((rule) => /(^|,)\s*\.gw-status-facts dt\s*$/m.test(rule.selector.replace(/\s+/g, " ")));

    expect(owning.length).toBeGreaterThan(0);
    for (const rule of owning) {
      const declared = /padding-bottom\s*:\s*([^;]+)/.exec(rule.body);
      if (!declared) continue;
      expect(declared[1]?.trim(), `${rule.selector} { padding-bottom }`).not.toMatch(/^0(px)?$/);
    }
  });
});

describe("Accounts is a section of this page, for an owner and for nobody else", () => {
  const ACCOUNT = {
    user_id: "usr_owner",
    username: "ryan",
    role: "owner",
    state: "active",
    created_at: "2026-08-01T10:00:00Z",
    created_by: "console",
    password_changed_at: "2026-08-01T10:00:00Z",
    last_login_at: "2026-09-01T09:30:00Z",
    disabled_at: null,
    disabled_by: null,
    sessions_live: 1,
  };

  function routed(input: string): Response {
    if (input.includes("/v1/users")) return envelope([ACCOUNT]);
    if (input.includes("/v1/sessions")) return envelope([]);
    return envelope(PAYLOAD);
  }

  it("renders the section for an owner, after the disclosures", async () => {
    vi.stubGlobal("fetch", (input: string) => Promise.resolve(routed(input)));

    await mountStatusPage(host, { onForbidden, role: "owner" });

    expect([...host.querySelectorAll("section h2")].map((heading) => heading.textContent)).toEqual([
      "Deployment",
      "Architecture",
      "Data footprint",
      "Scheduled work",
      "Source polls & freshness",
      "Observability boundaries",
      "Accounts",
    ]);
    // `?view=status#accounts` is the deep link, so the section has to be addressable.
    expect(host.querySelector("#accounts")).not.toBeNull();
    expect(host.querySelector('[data-user="ryan"]')).not.toBeNull();
  });

  it("renders no section, and asks nothing, for a viewer or an unresolved reader", async () => {
    const fetch = vi.fn(() => Promise.resolve(envelope(PAYLOAD)));
    vi.stubGlobal("fetch", fetch);

    await mountStatusPage(host, { onForbidden, role: "viewer" });

    expect(host.querySelector("#accounts")).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(1);

    await mountStatusPage(host, { onForbidden });

    expect(host.querySelector("#accounts")).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});

describe("the three residuals an allocation publishes about itself", () => {
  function withAllocationChecks(state: "ok" | "degraded" | "unavailable"): StatusPayload {
    return {
      ...PAYLOAD,
      checks: [
        ...PAYLOAD.checks,
        {
          id: "allocation_conservation",
          label: "Allocation conservation",
          state,
          observed_at: PAYLOAD.observed_at,
          detail: "TX: 0.0012 of lease volume has no eligible well to carry it.",
          tier: "data",
          probe: "cr_tx_allocation_v0_1",
        },
        {
          id: "crosswalk_agreement",
          label: "Crosswalk agreement",
          state: "ok",
          observed_at: PAYLOAD.observed_at,
          detail: "TX: the two published crosswalks are compared across 14 districts.",
          tier: "data",
          probe: "cr_tx_ewa_role_1",
        },
        {
          id: "allocation_error_bounds",
          label: "Allocation error bounds",
          state: "ok",
          observed_at: PAYLOAD.observed_at,
          detail: "Measured on MT over 132 lease-months; not yet transferable to TX.",
          tier: "data",
          probe: "cr_alloc_v0_error_bounds_1",
        },
      ],
    };
  }

  it("renders all three in the data tier", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(envelope(withAllocationChecks("ok"))));
    await mountStatusPage(host, { onForbidden });

    const labels = [...host.querySelectorAll(".gw-status-check h4")].map(
      (node) => node.textContent,
    );
    expect(labels).toContain("Allocation conservation");
    expect(labels).toContain("Crosswalk agreement");
    expect(labels).toContain("Allocation error bounds");
  });

  it("names the jurisdiction and the rule on every row", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(envelope(withAllocationChecks("ok"))));
    await mountStatusPage(host, { onForbidden });

    const rows = [...host.querySelectorAll(".gw-status-check")].filter((node) =>
      node.textContent?.includes("cr_tx_allocation_v0_1"),
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]?.textContent).toContain("TX:");
  });

  it("draws a failing check amber rather than dropping the row", async () => {
    // A row that vanishes reads as a surface nobody built. These exist so a reader can see
    // that an estimate is being served and how far it can be out.
    vi.stubGlobal("fetch", () => Promise.resolve(envelope(withAllocationChecks("degraded"))));
    await mountStatusPage(host, { onForbidden });

    const row = [...host.querySelectorAll(".gw-status-check")].find((node) =>
      node.textContent?.includes("Allocation conservation"),
    );
    expect(row).not.toBeUndefined();
    expect(row?.querySelector(".gw-status-badge")?.getAttribute("data-state")).toBe(
      "degraded",
    );
  });
});
