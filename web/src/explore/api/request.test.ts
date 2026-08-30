// @vitest-environment happy-dom
import { readFileSync } from "node:fs";

import { beforeEach, describe, expect, it } from "vitest";

import { DEFAULT_STATE } from "../../app/state.ts";
import { buildCatalogue } from "../catalogue.ts";
import { requestFor } from "../router.ts";
import { mountPane } from "./pane.ts";
import {
  DIALECTS,
  KEY_PLACEHOLDER,
  absoluteUrl,
  commandFor,
  curlFor,
  requestFrom,
  walkAllPages,
} from "./request.ts";

const SNAPSHOT = JSON.parse(readFileSync("../tests/contract/openapi_snapshot.json", "utf8"));
const CATALOGUE = buildCatalogue(SNAPSHOT);
const SOURCE = readFileSync("src/explore/api/request.ts", "utf8");
const KEY = "f".repeat(64);

const REQUEST = {
  operationId: "list_quarantine",
  path: "/v1/quarantine",
  query: { reason_code: ["key_incomplete", "unknown_vocab"], limit: ["100"] },
};

beforeEach(() => {
  document.body.innerHTML = '<aside id="pane"></aside>';
});

describe("three dialects come from one request object (§4.2, 9.2)", () => {
  it("renders the same absolute URL in all three, and no hand-maintained template", () => {
    const rendered = DIALECTS.map((dialect) => commandFor(REQUEST, dialect));
    const url = absoluteUrl(REQUEST);

    expect(url).toBe(
      `${window.location.origin}/v1/quarantine?reason_code=key_incomplete&reason_code=unknown_vocab&limit=100`,
    );
    for (const command of rendered) expect(command).toContain(url);
    expect(new Set(rendered).size).toBe(3);
  });

  it("carries the placeholder in every dialect and a credential in none of them", () => {
    for (const dialect of DIALECTS) {
      const command = commandFor(REQUEST, dialect);
      expect(command, dialect).toContain(KEY_PLACEHOLDER);
      expect(command, dialect).not.toContain(KEY);
    }
  });

  // The machine path deliberately keeps X-Glasswell-Key: a copied snippet runs outside the
  // browser, where the session cookie does not exist. What it may never do is read one.
  it("never reads a credential at all, which is why it cannot render one", () => {
    expect(SOURCE).not.toMatch(/\bauthHeaders\b|localStorage|document\.cookie/);
  });

  it("keeps a repeated filter repeated, because that is what was on the wire", () => {
    const url = absoluteUrl(REQUEST);

    expect(url.split("reason_code=")).toHaveLength(3);
  });

  it("builds from what the router returned, so the pane cannot drift from the grid (9.6)", () => {
    const dataset = CATALOGUE.datasets.find((one) => one.id === "quarantine");
    const state = {
      ...DEFAULT_STATE,
      view: "explore" as const,
      ds: "quarantine",
      extra: { "f.state": ["open"], as_of: ["2026-08-01"] },
    };
    const request = requestFor(dataset as never, state);

    expect(commandFor(request, "curl")).toContain(
      `${window.location.origin}/v1/quarantine?state=open&as_of=2026-08-01`,
    );
  });

  it("reads the next page out of links.next rather than assembling a cursor", () => {
    const next = requestFrom("list_quarantine", "/v1/quarantine?limit=2&cursor=eyJrIjoi");

    expect(next).toEqual({
      operationId: "list_quarantine",
      path: "/v1/quarantine",
      query: { limit: ["2"], cursor: ["eyJrIjoi"] },
    });
    expect(commandFor(next as never, "curl")).toContain("cursor=eyJrIjoi");
  });

  it("walks every page by following the link the server sent, not by counting", () => {
    const loop = walkAllPages(REQUEST);

    expect(loop).toContain(absoluteUrl(REQUEST));
    expect(loop).toContain(".links.next");
    expect(loop).toContain(KEY_PLACEHOLDER);
    expect(loop).not.toContain(KEY);
  });

  it("gives the breadcrumb the command it used to build itself (C8 N2)", () => {
    const step = { operationId: "get_quarantine_row", request: { path: "/v1/q/1", query: {} } };

    expect(curlFor(step)).toBe(commandFor({ ...step, ...step.request }, "curl"));
  });
});

describe("a failed request keeps its REQUEST block (§4.7)", () => {
  it("renders the command that failed beside the problem, not instead of it", () => {
    const host = document.getElementById("pane") as HTMLElement;
    mountPane(host, {
      document: SNAPSHOT,
      state: { ...DEFAULT_STATE, view: "explore", ds: "quarantine" },
      onSections: () => undefined,
      signal: new AbortController().signal,
      call: {
        state: "failed",
        role: "collection",
        dataset: CATALOGUE.datasets.find((one) => one.id === "quarantine") as never,
        request: { operationId: "list_quarantine", path: "/v1/quarantine", query: { limit: ["1"] } },
        envelope: null,
        error: new Error("network"),
        meta: { status: 503, headers: new Headers(), elapsed_ms: 12 },
      },
    });

    const command = document.querySelector('.gw-api-command[data-dialect="curl"]')?.textContent;
    expect(command).toContain("/v1/quarantine?limit=1");
    expect(document.querySelector(".gw-api-status")?.textContent).toContain("503");
  });
});
