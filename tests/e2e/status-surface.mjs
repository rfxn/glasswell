import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { BREAKPOINTS, chromeExecutable, instrumentedPage, launch, redact } from "./lib.mjs";

const DIST = fileURLToPath(new URL("../../web/dist/", import.meta.url));
const DIST_ROOT = normalize(DIST).replace(/[\\/]+$/, "");
const REQUIRE = process.env.GLASSWELL_REQUIRE_E2E === "1";
const STATUS_BREAKPOINTS = [...BREAKPOINTS, { width: 320, height: 568 }];
const MIME = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

const STATUS = {
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
      id: "restore",
      label: "Restore drill",
      state: "not_instrumented",
      observed_at: null,
      detail: "No persisted execution result exists.",
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
          value: 7223544,
          unit: "rows",
          precision: "estimated",
          reason: "Operational inventory at the named grain, not a petroleum measurement.",
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
      cadence: "Every 35 days",
      freshness_reason:
        "The latest poll completed unchanged inside cadence; the older artifact remains current because its bytes were rechecked successfully.",
    },
  ],
  platform: {
    code_version: "v0.55+abcdef0",
    schema_version: 44,
    schema_version_reason: "Schema migration sequence is deployment bookkeeping.",
    database_bytes: 12345678,
    database_bytes_reason: "Operational storage reading, not a petroleum measurement.",
  },
  disclosures: [
    {
      id: "remote-backup",
      label: "Remote backup",
      state: "limited",
      detail: "The application cannot observe remote-copy completion.",
    },
  ],
};

let passed = 0;
let failed = 0;
const ok = (label) => {
  passed += 1;
  console.log(`  ok   ${String(passed + failed).padStart(2)} ${label}`);
};
const bad = (label, detail) => {
  failed += 1;
  console.log(`  FAIL ${String(passed + failed).padStart(2)} ${label} — ${redact(detail)}`);
};
const assert = (condition, label, detail) => (condition ? ok(label) : bad(label, detail));

function unavailable(reason) {
  if (REQUIRE) {
    console.error(`GLASSWELL_REQUIRE_E2E is set but ${reason}`);
    process.exit(1);
  }
  console.log(`status-surface skipped: ${reason}`);
  process.exit(0);
}

try {
  await import("playwright-core");
} catch {
  unavailable("playwright-core is not installed (npm --prefix tests/e2e install)");
}
if (!chromeExecutable()) unavailable("no chromium build found (set GW_CHROME)");

function envelope(data) {
  return JSON.stringify({ data, meta: {}, links: {} });
}

function staticServer() {
  return createServer(async (request, response) => {
    try {
      const pathname = new URL(request.url ?? "/", "http://127.0.0.1").pathname;
      const relative = pathname === "/" ? "index.html" : decodeURIComponent(pathname.slice(1));
      const path = normalize(join(DIST, relative));
      if (path !== DIST_ROOT && !path.startsWith(`${DIST_ROOT}${sep}`)) {
        throw new Error("path escaped dist");
      }
      const body = await readFile(path);
      response.writeHead(200, {
        "content-type": MIME[extname(path)] ?? "application/octet-stream",
        "cache-control": "no-store",
      });
      response.end(body);
    } catch {
      response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
      response.end("not found");
    }
  });
}

const server = staticServer();
await new Promise((resolve, reject) => {
  server.once("error", reject);
  server.listen(0, "127.0.0.1", resolve);
});
const address = server.address();
if (!address || typeof address === "string") throw new Error("status server has no TCP address");
const base = `http://127.0.0.1:${address.port}`;

const browser = await launch();
try {
  for (const viewport of STATUS_BREAKPOINTS) {
    const at = `${viewport.width}x${viewport.height}`;
    const { context, page, journal } = await instrumentedPage(browser, {
      viewport,
      auth: false,
      origin: base,
    });
    const apiFixture = async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/v1/status") {
        await route.fulfill({ status: 200, contentType: "application/json", body: envelope(STATUS) });
        return;
      }
      if (path === "/v1") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope({ published_vintages: [{ vintage_date: "2026-08-26" }] }),
        });
        return;
      }
      if (path === "/v1/glossary/index") {
        await route.fulfill({ status: 200, contentType: "application/json", body: envelope({ terms: [] }) });
        return;
      }
      if (path === "/v1/glossary") {
        await route.fulfill({ status: 200, contentType: "application/json", body: envelope([]) });
        return;
      }
      await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
    };
    await page.route("**/v1", apiFixture);
    await page.route("**/v1/**", apiFixture);

    await page.goto(`${base}/?view=status`, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForSelector("#gw-status-page:not([hidden]) .gw-status-page", { timeout: 10000 });
    await page.waitForFunction(
      () => document.querySelector(".gw-status-dataset, .gw-status-error"),
      undefined,
      { timeout: 10000 },
    );
    const errorPanel = page.locator(".gw-status-error");
    const renderedError = (await errorPanel.count()) > 0 ? await errorPanel.textContent() : null;
    if (renderedError) throw new Error(`${at} Status fixture failed to render: ${renderedError}`);
    await page.waitForTimeout(200);

    const seen = await page.evaluate(() => {
      const rect = (selector) => {
        const node = document.querySelector(selector);
        if (!node) return null;
        const box = node.getBoundingClientRect();
        return { left: box.left, right: box.right, top: box.top, bottom: box.bottom, width: box.width, height: box.height };
      };
      const intersects = (a, b) =>
        a && b && Math.min(a.right, b.right) > Math.max(a.left, b.left) && Math.min(a.bottom, b.bottom) > Math.max(a.top, b.top);
      const buttons = [...document.querySelectorAll(".gw-mode-btn")].map((button) => {
        const box = button.getBoundingClientRect();
        return { label: button.textContent, width: box.width, height: box.height };
      });
      const major = [rect(".gw-brand"), rect(".gw-mode-switch"), rect(".gw-controls")].filter(Boolean);
      return {
        documentOverflow: document.documentElement.scrollWidth - innerWidth,
        headerOverflow: document.getElementById("gw-header").scrollWidth - document.getElementById("gw-header").clientWidth,
        majorOverlap: major.some((one, index) => major.slice(index + 1).some((two) => intersects(one, two))),
        buttons,
        selected: document.querySelector('.gw-mode-btn[data-view="status"]')?.getAttribute("aria-pressed"),
        markVisible: rect(".gw-mark")?.width > 0,
        brandLabel: document.querySelector(".gw-brand")?.getAttribute("aria-label"),
        wordmarkDisplay: getComputedStyle(document.querySelector(".gw-brand-text")).display,
        statusOverflow:
          document.getElementById("gw-status-page").scrollWidth - document.getElementById("gw-status-page").clientWidth,
        mapHidden: document.getElementById("gw-map")?.hidden,
        mapCanvases: document.querySelectorAll("#gw-map canvas").length,
        semantic: {
          sections: document.querySelectorAll("#gw-status-page section[aria-labelledby]").length,
          lists: document.querySelectorAll("#gw-status-page dl").length,
          tables: document.querySelectorAll("#gw-status-page table").length,
          times: document.querySelectorAll("#gw-status-page time[datetime]").length,
        },
        sourceDisclosure: document.getElementById("gw-status-sources-title")?.parentElement?.textContent,
      };
    });

    assert(seen.documentOverflow <= 0, `${at} document has no horizontal overflow`, `${seen.documentOverflow}px`);
    assert(seen.headerOverflow <= 0, `${at} header stays inside its rail`, `${seen.headerOverflow}px`);
    assert(!seen.majorOverlap, `${at} brand, surfaces, and controls do not overlap`, JSON.stringify(seen));
    assert(
      seen.buttons.map((button) => button.label).join(",") === "Map,Explore,Status",
      `${at} all three surface labels are visible`,
      JSON.stringify(seen.buttons),
    );
    assert(seen.selected === "true", `${at} Status is the pressed surface`, `aria-pressed ${seen.selected}`);
    assert(seen.markVisible && seen.brandLabel?.includes("glasswell"), `${at} the mark keeps its accessible brand`, JSON.stringify(seen));
    if (viewport.width <= 390) {
      assert(seen.wordmarkDisplay === "none", `${at} wordmark text yields while the mark remains`, seen.wordmarkDisplay);
      assert(
        seen.buttons.every((button) => button.width >= 44 && button.height >= 44),
        `${at} every surface remains a touch target`,
        JSON.stringify(seen.buttons),
      );
    }
    assert(seen.statusOverflow <= 0, `${at} Status owns no page-level horizontal overflow`, `${seen.statusOverflow}px`);
    assert(seen.mapHidden && seen.mapCanvases === 0, `${at} direct Status arrival never constructs Map`, JSON.stringify(seen));
    assert(
      seen.semantic.sections >= 6 && seen.semantic.lists >= 3 && seen.semantic.tables === 2 && seen.semantic.times >= 4,
      `${at} semantic sections, lists, tables, and times survive layout`,
      JSON.stringify(seen.semantic),
    );
    assert(
      seen.sourceDisclosure?.includes("failed or interrupted checks cannot"),
      `${at} source freshness states the durable-outcome limit`,
      seen.sourceDisclosure ?? "missing source section",
    );
    assert(
      seen.sourceDisclosure?.includes("2026-05-01") && seen.sourceDisclosure?.includes("mf_nd_01"),
      `${at} source freshness retains declared vintage and artifact identity`,
      seen.sourceDisclosure ?? "missing source section",
    );
    assert(journal.pageerror.length === 0, `${at} no page errors`, journal.pageerror.join(" | "));
    assert(journal.console.length === 0, `${at} no console warnings or errors`, journal.console.join(" | "));
    assert(journal.nonok.length === 0, `${at} no failed network responses`, journal.nonok.join(" | "));

    await context.close();
  }
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
