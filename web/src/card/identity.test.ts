// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Envelope } from "../api/envelope.ts";
import { renderIdentity } from "./identity.ts";
import type { StatusHistory, WellIdentity } from "./identity.ts";

const ND: WellIdentity = {
  api10: "3305300001",
  state_code: "33",
  status_reported: "PA",
  status_canonical: "plugged",
  status_vocabulary_rule: "cr_nd_status_vocab_1",
  well_type_reported: "OG",
  producing: "not_producing",
  geometry: [{ geom_type: "lateral", geom_key: "33053000010000_LAT1", source_datum: "EPSG:4269" }],
  geometry_provenance: ["lateral"],
  geometry_provenance_rule: "cr_nd_geometry_provenance_1",
  jurisdiction_name: "North Dakota",
  regulator_name: "ND Dept. of Mineral Resources, Oil and Gas Division",
  regulator_url: "https://www.dmr.nd.gov/oilgas/mprindex.asp",
};

const envelope = (
  data: Partial<WellIdentity>,
  links: Record<string, string> = {},
): Envelope<WellIdentity> =>
  ({
    data: { ...ND, ...data },
    meta: { as_of: { requested: "latest", resolved: "2026-08-20" }, warnings: [], labels: {} },
    links: { self: "/v1/wells/3305300001", status_rule: "/v1/conformance/cr_nd_status_vocab_1", ...links },
  }) as unknown as Envelope<WellIdentity>;

const HISTORY: StatusHistory = {
  api10: "0512324638",
  basis: {
    clock: "source_valid_time",
    served: true,
    rule_id: "cr_co_wells_status_history_1",
    status_vocabulary_rule: "cr_co_wells_status_vocab_1",
    class_column_label: "class as glasswell maps this code today",
    class_column_is_historical: false,
    detail: "The dates beside these codes are the regulator's own.",
  },
  history: [
    {
      effective_from: "2024-11-18",
      status_reported: "SI",
      status_canonical: "inactive",
      status_rule_id: "cr_co_wells_status_vocab_1",
    },
    {
      effective_from: "2019-04-02",
      status_reported: "PR",
      status_canonical: "active",
      status_rule_id: "cr_co_wells_status_vocab_1",
    },
  ],
  cap: { limit: 10, returned: 2, total: 2, withheld: 0 },
};

let host: HTMLElement;
let bands: HTMLElement;

const render = (
  data: Partial<WellIdentity>,
  links: Record<string, string> = {},
): Promise<void> => renderIdentity(host, envelope(data, links), bands, {});

const text = (): string => host.textContent ?? "";

beforeEach(() => {
  document.body.replaceChildren();
  host = document.createElement("div");
  bands = document.createElement("div");
  bands.className = "gw-card-facts";
  document.body.appendChild(host);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("whose well it is", () => {
  it("names the jurisdiction and its regulator, and links the regulator", async () => {
    await render({});
    const link = host.querySelector<HTMLAnchorElement>(".gw-identity-regulator");
    expect(text()).toContain("North Dakota");
    expect(link?.textContent).toBe("ND Dept. of Mineral Resources, Oil and Gas Division");
    expect(link?.getAttribute("href")).toBe("https://www.dmr.nd.gov/oilgas/mprindex.asp");
  });

  it("says the link is a portal, because no per-well template is registered anywhere", async () => {
    // A link labelled "the regulator's record for this well" that lands on a downloads index
    // is a lie the size of one click.
    await render({});
    expect(text()).toContain("portal, not this well's own record");
  });

  it("reads a well type as its own regulator filed it", async () => {
    // The hover was a bare code, so a Montana disposal well read as North Dakota filed it.
    await render({});
    expect(host.querySelector(".gw-identity-well-type")?.textContent).toBe(
      "OG · as ND Dept. of Mineral Resources, Oil and Gas Division filed it",
    );
  });

  it("keeps the fact bands the card built, rather than replacing them", async () => {
    bands.appendChild(document.createElement("dl"));
    await render({});
    expect(host.contains(bands)).toBe(true);
  });
});

describe("DR-A7: the status is never blank", () => {
  it("renders the filed code and the class where the class resolves", async () => {
    await render({});
    expect(host.querySelector(".gw-identity-filed")?.textContent).toContain("PA");
    expect(host.querySelector(".gw-identity-class")?.textContent).toContain("plugged");
  });

  it("renders the filed code and says unmapped where no rule maps it", async () => {
    // Measured on the deployed instance: 68,186 Texas wells resolve to no class, and the chip
    // in the card's head is built only when one does, so they showed no status at all.
    await render({
      state_code: "42",
      status_reported: "AC",
      status_canonical: null,
      status_vocabulary_rule: "cr_tx_status_vocab_1",
      jurisdiction_name: "Texas",
      regulator_name: "Texas Railroad Commission",
    });
    const klass = host.querySelector(".gw-identity-class");
    expect(host.querySelector(".gw-identity-filed")?.textContent).toContain("AC");
    expect(klass?.textContent).toContain("unmapped");
    expect(klass?.classList.contains("gw-absent")).toBe(true);
    expect(klass?.querySelector(".gw-identity-rule")?.textContent).toBe("cr_tx_status_vocab_1");
  });

  it("separates a code nobody mapped from no code at all", async () => {
    await render({ status_reported: null, status_canonical: null });
    expect(host.querySelector(".gw-identity-filed")?.textContent).toContain("none filed");
    expect(host.querySelector(".gw-identity-class")?.textContent).toContain("unresolved");
  });

  it("names the regulator beside the filed code, whatever the class does", async () => {
    await render({ status_canonical: null });
    expect(host.querySelector(".gw-identity-filed")?.textContent).toContain(
      "as ND Dept. of Mineral Resources, Oil and Gas Division filed it",
    );
  });
});

describe("what the spine knows and the card did not show", () => {
  it("brings producing, the state prefix and the geometry list to the section", async () => {
    await render({});
    expect(text()).toContain("not_producing");
    expect(text()).toContain("33");
    expect(host.querySelector(".gw-identity-geometry")?.textContent).toBe(
      "lateral (EPSG:4269)",
    );
  });

  it("states the registry gap where a jurisdiction registers no geometry rule", async () => {
    // Texas has no geometry_provenance row today. Inheriting North Dakota's is the mislabel
    // this section exists to end.
    await render({ geometry_provenance_rule: null, state_code: "42" });
    expect(text()).toContain("registers no geometry provenance rule");
    expect(text()).not.toContain("cr_nd_geometry_provenance_1");
  });
});

describe("the status history", () => {
  it("is not asked for where the response offered no link to it", async () => {
    const fetched = vi.fn();
    vi.stubGlobal("fetch", fetched);
    await render({});
    expect(fetched).not.toHaveBeenCalled();
    expect(text()).toContain("not a date the regulator stamped");
    // §2.3: a North Dakota well says North Dakota files a snapshot, off the served field the
    // row above already prints, never a literal this file knows.
    expect(text()).toContain("North Dakota files a snapshot");
    expect(host.querySelector(".gw-identity-rule")?.getAttribute("href")).toContain(
      "/v1/conformance/",
    );
  });

  it("draws the filed codes newest first, with the class column labelled for what it is", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ data: HISTORY, meta: { as_of: {}, warnings: [], labels: {} }, links: {} }), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        ),
      ),
    );

    await render({ state_code: "05" }, { history: "/v1/wells/0512324638/history" });

    const headers = [...host.querySelectorAll("th")].map((cell) => cell.textContent);
    expect(headers).toEqual([
      "Effective from",
      "Filed code",
      "class as glasswell maps this code today",
    ]);
    const codes = [...host.querySelectorAll("tbody tr")].map(
      (line) => line.children[1]?.textContent,
    );
    expect(codes).toEqual(["SI", "PR"]);
    // Every row names the rule that produced its class, so a copied row keeps its provenance.
    for (const line of host.querySelectorAll("tbody tr")) {
      expect(line.querySelector(".gw-identity-rule")?.textContent).toBe(
        "cr_co_wells_status_vocab_1",
      );
    }
    expect(text()).toContain("today's mapping applied to a historical code");
  });

  it("names an unnamed jurisdiction as one rather than inventing a name", async () => {
    vi.stubGlobal("fetch", vi.fn());
    await render({ jurisdiction_name: null });
    expect(text()).toContain("This jurisdiction files a snapshot");
  });

  it("hovers the history's own columns from the labels the router serves for them", async () => {
    // M3: the pointers exist on the wire and had no consumer, so the header could never
    // highlight whatever the glossary seeded.
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              data: HISTORY,
              meta: {
                as_of: {},
                warnings: [],
                labels: {
                  "/history/effective_from": "gt_effective_date",
                  "/history/status_reported": "gt_well_status",
                  "/history/status_canonical": "gt_well_status",
                },
              },
              links: {},
            }),
            { status: 200, headers: { "content-type": "application/json" } },
          ),
        ),
      ),
    );

    await render({ state_code: "05" }, { history: "/v1/wells/0512324638/history" });

    expect([...host.querySelectorAll("th .gw-label")].map((node) => node.getAttribute("term-id"))).toEqual([
      "gt_effective_date",
      "gt_well_status",
      "gt_well_status",
    ]);
  });

  it("says what the cap held back rather than letting a short list read as a short life", async () => {
    const capped = {
      ...HISTORY,
      cap: { limit: 10, returned: 10, total: 14, withheld: 4 },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ data: capped, meta: { as_of: {}, warnings: [], labels: {} }, links: {} }), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        ),
      ),
    );

    await render({}, { history: "/v1/wells/0512324638/history" });

    expect(text()).toContain("Showing 10 of 14 filed headers");
    expect(text()).toContain("4 older ones are not on this page");
  });
});
