import { describe, expect, it } from "vitest";

import { stubFetch } from "./fixtures.ts";

const body = async (answer: Response): Promise<unknown> => answer.json();

describe("the route a stubbed fetch answers a request with", () => {
  it("answers the longest match, whatever order the routes were declared in", async () => {
    // H-17. The map is prefix-matched in declaration order, so a shorter key declared first
    // swallowed every longer path beneath it: `/production` answered `/production/pools`, the
    // pools section rendered from a body with no filings in it and threw into its own catch,
    // and the browser suite read green over a major that was on screen at three widths.
    const fetch = stubFetch({
      "/v1/wells/33053/production": { series: "well" },
      "/v1/wells/33053/production/pools": { series: "pools" },
    });

    expect(await body(await fetch("/v1/wells/33053/production/pools"))).toEqual({
      series: "pools",
    });
    expect(await body(await fetch("/v1/wells/33053/production"))).toEqual({ series: "well" });
  });

  it("still matches on a prefix, so a query string reaches its path's own route", async () => {
    const fetch = stubFetch({ "/v1/wells/33053": { api10: "33053" } });

    expect(await body(await fetch("/v1/wells/33053?as_of=2026-09-02"))).toEqual({
      api10: "33053",
    });
  });

  it("answers 404 where no route matches, rather than the first one declared", async () => {
    const fetch = stubFetch({ "/v1/wells/33053": { api10: "33053" } });

    expect((await fetch("/v1/conformance/cr_nm_wcproduction_pool_rollup_2")).status).toBe(404);
  });
});
