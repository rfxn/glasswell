// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

import { completionContextEnvelope, stubFetch, wellEnvelope } from "../test/fixtures.ts";

const { renderWellCard } = await import("./card.ts");
const { renderNeighborRefusal } = await import("./neighbors.ts");

const API10 = "3305310451";

describe("a jurisdiction the neighbour mart's domain does not reach", () => {
  let host: HTMLElement;

  beforeEach(() => {
    document.body.replaceChildren();
    host = document.createElement("div");
    document.body.appendChild(host);
  });

  it("renders a third state that says why, rather than no section at all", async () => {
    const excluded = structuredClone(wellEnvelope);
    (excluded.data as Record<string, unknown>)["neighbors_reason"] = "neighbors_domain_not_covered";
    delete (excluded.links as Record<string, unknown>)["neighbors"];
    vi.stubGlobal("fetch", vi.fn(stubFetch({ [`/v1/wells/${API10}`]: excluded })));

    await renderWellCard(host, API10, { onExplain: vi.fn(), onClose: vi.fn() });

    const frame = host.querySelector(".gw-neighbor-context .gw-frame-body") as HTMLElement;
    expect(frame).not.toBeNull();
    expect(frame.dataset["state"]).toBe("not_covered");
    expect(frame.textContent).toContain("measured envelope");
    expect(frame.textContent).not.toContain("neighbors_domain_not_covered");
  });

  it("renders nothing where the jurisdiction never registered laterals", async () => {
    const unregistered = structuredClone(wellEnvelope);
    (unregistered.data as Record<string, unknown>)["neighbors_reason"] = null;
    delete (unregistered.links as Record<string, unknown>)["neighbors"];
    vi.stubGlobal("fetch", vi.fn(stubFetch({ [`/v1/wells/${API10}`]: unregistered })));

    await renderWellCard(host, API10, { onExplain: vi.fn(), onClose: vi.fn() });

    expect(host.querySelector(".gw-neighbor-context")).toBeNull();
  });

  it("falls back to the reason code's own title rather than inventing prose for it", () => {
    const rendered = renderNeighborRefusal("some_future_reason");

    expect(rendered.textContent).toBeTruthy();
    expect(rendered.textContent).not.toContain("some_future_reason");
  });
});

describe("a refusal both endpoints disclose", () => {
  let host: HTMLElement;

  beforeEach(() => {
    document.body.replaceChildren();
    host = document.createElement("div");
    document.body.appendChild(host);
  });

  it("says a withheld length once, not once per envelope that reports it", async () => {
    const well = structuredClone(wellEnvelope);
    (well.meta as { warnings: unknown[] }).warnings = [
      { code: "length_scope_unregistered", detail: "no length rule is registered", pointer: "/lateral_length_ft" },
    ];
    const completions = structuredClone(completionContextEnvelope);
    (completions.meta as { warnings: unknown[] }).warnings = [
      {
        code: "length_scope_unregistered",
        detail: "No length rule is registered for this well's basin",
        pointer: "/design/lateral_length_ft",
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn(
        stubFetch({
          [`/v1/wells/${API10}`]: well,
          [`/v1/wells/${API10}/completions`]: completions,
        }),
      ),
    );

    await renderWellCard(host, API10, { onExplain: vi.fn(), onClose: vi.fn() });

    const titles = [...host.querySelectorAll("summary, .gw-empty")].map((node) => node.textContent);
    const said = titles.filter((text) => text?.includes("Length scope unregistered"));
    expect(said).toHaveLength(1);
  });
});
