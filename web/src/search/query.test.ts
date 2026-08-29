import { describe, expect, it } from "vitest";

import { searchRequest, toResults } from "./query.ts";
import { wellEnvelope } from "../test/fixtures.ts";

const listEnvelope = {
  data: [
    {
      api10: "3302501169",
      well_name: "MANDAREE 30-31H",
      operator_name_reported: "MARATHON OIL COMPANY",
      status_canonical: "active",
      county_code_at_permit: "025",
    },
  ],
  meta: {},
  links: {},
};

describe("searchRequest", () => {
  it("routes a ten-digit term to the well itself, not to a name substring", () => {
    // A name search for "3305310451" returns nothing: `q` matches well_name only.
    expect(searchRequest("3305310451")).toEqual({ path: "/v1/wells/3305310451", query: {} });
  });

  it("routes any other term to the q filter with a bounded page", () => {
    expect(searchRequest("mandaree")).toEqual({
      path: "/v1/wells",
      query: { q: "mandaree", limit: "20" },
    });
  });

  it("trims the term before deciding, so a pasted api10 still resolves", () => {
    expect(searchRequest("  3305310451 ")).toEqual({ path: "/v1/wells/3305310451", query: {} });
  });

  it("refuses an empty or whitespace term rather than listing every well", () => {
    expect(searchRequest("   ")).toBeNull();
  });

  it("routes a pasted api14 to the spine filter, which the path cannot take and q cannot match", () => {
    expect(searchRequest("33053104510000")).toEqual({
      path: "/v1/wells",
      query: { api10: "33053104510000", limit: "20" },
    });
  });

  it("treats an eleven-digit term as a name substring, not an api10", () => {
    expect(searchRequest("33053104510")).toEqual({
      path: "/v1/wells",
      query: { q: "33053104510", limit: "20" },
    });
  });
});

describe("toResults", () => {
  it("reads the list shape", () => {
    expect(toResults(listEnvelope)).toEqual([
      {
        api10: "3302501169",
        name: "MANDAREE 30-31H",
        operator: "MARATHON OIL COMPANY",
        status: "active",
      },
    ]);
  });

  it("reads the single-well shape as a one-row list", () => {
    const results = toResults(wellEnvelope);

    expect(results).toHaveLength(1);
    expect(results[0]?.api10).toBe("3305310451");
    expect(results[0]?.name).toBe("Mandaree 50-2008H");
  });

  it("falls back to the api10 when a well has no name", () => {
    const anonymous = { data: [{ api10: "3305310451", well_name: null }], meta: {}, links: {} };

    expect(toResults(anonymous)[0]?.name).toBe("3305310451");
  });

  it("returns nothing for an envelope with no data", () => {
    expect(toResults({ data: [] })).toEqual([]);
  });
});

/**
 * UDM-SPEC §4.3 and §7.3 chunk 1.5. The key is `(authority, native_id)` and the API-10 is its
 * United States instantiation, so a row is a well when it carries *an* identifier — not when it
 * carries that one. The guard used to require `api10`, which would drop a non-US well silently:
 * no row, no error, and a search that says "no well matches" about a well that exists.
 */
describe("toResults reads the general key, not only its US instantiation", () => {
  const envelope = (row: Record<string, unknown>) => ({ data: [row], meta: {}, links: {} });

  it("still keeps a row that carries only an api10", () => {
    const results = toResults(envelope({ api10: "3305310451", well_name: "MANDAREE 30-31H" }));

    expect(results).toHaveLength(1);
    expect(results[0]?.api10).toBe("3305310451");
  });

  it("keeps a well identified by its authority and native id, with no api10 to give", () => {
    const results = toResults(
      envelope({ authority: "ca-ab", native_id: "0209070806W400", well_name: "SYNTHETIC 1" }),
    );

    expect(results).toHaveLength(1);
    expect(results[0]?.name).toBe("SYNTHETIC 1");
    // §5.3 ground two: a field named api10 never carries a non-API-10. Absent says absent.
    expect(results[0]?.api10).toBeNull();
  });

  it("labels such a well with the identifier it does answer to, never `undefined` (N-6)", () => {
    const results = toResults(envelope({ authority: "ca-ab", native_id: "0209070806W400" }));

    expect(results[0]?.name).toBe("0209070806W400");
  });

  it("reads a well_id or a uwi the same way, so a later wave adds no branch here", () => {
    expect(toResults(envelope({ well_id: "wl_0af31c" }))[0]?.name).toBe("wl_0af31c");
    expect(toResults(envelope({ uwi: "100062503507W400" }))[0]?.name).toBe("100062503507W400");
  });

  it("drops a row that identifies no well at all rather than rendering a blank option", () => {
    expect(toResults(envelope({ well_name: "NAMED BUT UNIDENTIFIED" }))).toEqual([]);
    expect(toResults(envelope({ authority: "ca-ab" }))).toEqual([]);
    expect(toResults(envelope({ api10: 3305310451 }))).toEqual([]);
    expect(toResults(envelope({ api10: "" }))).toEqual([]);
  });

  /**
   * gate-udmw1 F-3: dropping the row was only half the fix. When another identifier keeps the
   * row alive, `?? null` does not catch `""`, so the field contract this same change added —
   * absent says absent — was broken by the value it was written to exclude. `main.ts:185` hands
   * this straight to `selectWell`, where `null` is the deselect signal, and `""` is neither a
   * well nor a deselect.
   */
  it("emits a null api10, never an empty one, when another identifier carries the row", () => {
    const carried = toResults(envelope({ api10: "", native_id: "0209070806W400" }));
    const named = toResults(envelope({ api10: "", well_id: "wl_0af31c", well_name: "X 1" }));

    expect(carried).toHaveLength(1);
    expect(carried[0]?.api10).toBeNull();
    expect(carried[0]?.name).toBe("0209070806W400");
    expect(named[0]?.api10).toBeNull();
    expect(named[0]?.name).toBe("X 1");
  });
});
