// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client.ts";
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
    },
    {
      id: "backup",
      label: "Remote backup",
      state: "not_instrumented",
      observed_at: null,
      detail: "No persisted remote-copy result exists.",
    },
  ],
  datasets: [
    {
      dataset_id: "canonical.production_monthly",
      label: "Production observations",
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
      ],
      valid_from: "2015-05",
      valid_to: "2026-03",
      detail: "Append-only source observations; not a count of unique wells.",
    },
  ],
  jobs: [
    {
      id: "source-refresh",
      label: "Source refresh",
      state: "pending",
      last_run_at: "2026-08-26T04:30:00Z",
      next_run_at: null,
      detail: "Next-run time is not persisted.",
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
  window.localStorage.setItem("glasswell.key", "f".repeat(64));
});

afterEach(() => {
  unmountStatusPage();
  vi.unstubAllGlobals();
  window.localStorage.clear();
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
    expect([...host.querySelectorAll("section > h2")].map((heading) => heading.textContent)).toEqual([
      "Infrastructure checks",
      "Dataset inventory",
      "Scheduled work",
      "Source polls & freshness",
      "Observability boundaries",
    ]);
    expect(host.querySelectorAll("dl").length).toBeGreaterThan(2);
    expect(host.querySelectorAll("table")).toHaveLength(2);
    expect(host.querySelectorAll("time").length).toBeGreaterThan(4);
    expect(host.querySelector("time")?.getAttribute("datetime")).toBe(PAYLOAD.observed_at);
    expect(host.textContent).toContain("Unchanged checks can keep older bytes current");
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
    expect(host.textContent).toContain("not a count of unique wells");
    expect(host.textContent).toContain("Not instrumented");
  });

  it("renders served operational reasons through gw-count", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(envelope(PAYLOAD)));

    await mountStatusPage(host, { onForbidden });

    const counts = [...host.querySelectorAll("gw-count")];
    expect(counts).toHaveLength(5);
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
    await vi.waitFor(() => expect(host.textContent).toContain("Production observations"));
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
