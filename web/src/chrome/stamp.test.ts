// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import config from "../../vite.config.ts";
import { buildStamp, mountBuildStamp, readStamp } from "./stamp.ts";

const define = (config as { define?: Record<string, string> }).define ?? {};

let host: HTMLElement;

function mount(stamp?: { hash: string; date: string }): HTMLElement {
  host = document.createElement("p");
  document.body.appendChild(host);
  if (stamp) mountBuildStamp(host, stamp);
  else mountBuildStamp(host);
  return host;
}

describe("the build stamp is a build-time constant, not a runtime question", () => {
  it("is injected by the config, so no request has to be made for it", () => {
    // A version the rail fetches is a version the rail cannot show while the API is down —
    // which is exactly when the reader wants to know what they are looking at.
    const injected = JSON.parse(define["__GW_BUILD__"] ?? "null") as { hash: string; date: string };

    expect(injected.hash).toMatch(/^(dev|[0-9a-f]{7,40}\+?)$/);
    expect(injected.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("says dev rather than nothing when there was no git to ask", () => {
    // A release archive is not a checkout. An empty corner reads as a broken rail; `dev` reads
    // as what it is.
    expect(readStamp(undefined)).toEqual({ hash: "dev", date: "" });
    expect(readStamp("3b83fcb")).toEqual({ hash: "dev", date: "" });
  });

  it("refuses a hash that is not one, so a broken define cannot paint prose in the corner", () => {
    expect(readStamp({ hash: "not a hash", date: "2026-08-21" }).hash).toBe("dev");
    expect(readStamp({ hash: "", date: "2026-08-21" }).hash).toBe("dev");
  });

  it("keeps the dirty marker, because a stamp that rounds to the commit is a lie", () => {
    expect(readStamp({ hash: "3b83fcb+", date: "2026-08-21" }).hash).toBe("3b83fcb+");
  });

  it("drops a date it cannot read rather than showing it", () => {
    expect(readStamp({ hash: "3b83fcb", date: "last tuesday" }).date).toBe("");
  });

  it("resolves the injected value at runtime", () => {
    expect(buildStamp().hash).toMatch(/^(dev|[0-9a-f]{7,40}\+?)$/);
  });
});

describe("the stamp in the rail", () => {
  it("shows the hash compactly and keeps the detail in the tooltip", () => {
    mount({ hash: "3b83fcb", date: "2026-08-21" });

    expect(host.querySelector(".gw-build-hash")?.textContent).toBe("3b83fcb");
    expect(host.textContent).toBe("build 3b83fcb");
    expect(host.title).toBe("build 3b83fcb · built 2026-08-21");
  });

  it("labels itself in its own element, so the rail can drop the word and keep the hash", () => {
    // Same shape as the as_of eyebrow: at 390 the column is 84 px and the label is the part
    // the reader can infer.
    mount({ hash: "3b83fcb", date: "2026-08-21" });

    expect(host.querySelector(".gw-build-label")?.textContent).toBe("build");
  });

  it("says in the tooltip that the tree was dirty, since the hash alone cannot", () => {
    mount({ hash: "3b83fcb+", date: "2026-08-21" });

    expect(host.title).toContain("uncommitted changes");
  });

  it("renders a dev build honestly and without a date it does not have", () => {
    mount({ hash: "dev", date: "" });

    expect(host.textContent).toBe("build dev");
    expect(host.title).toBe("build dev");
  });

  it("is written once: a second mount replaces it rather than stacking a second hash", () => {
    mount({ hash: "3b83fcb", date: "2026-08-21" });
    mountBuildStamp(host, { hash: "aaaaaaa", date: "2026-08-22" });

    expect(host.querySelectorAll(".gw-build-hash")).toHaveLength(1);
    expect(host.textContent).toBe("build aaaaaaa");
  });
});
