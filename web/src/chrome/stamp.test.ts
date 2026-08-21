// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import config from "../../vite.config.ts";
import {
  buildStamp,
  changelogHref,
  DEV_VERSION,
  mountBuildStamp,
  readStamp,
  stampText,
} from "./stamp.ts";

const define = (config as { define?: Record<string, string> }).define ?? {};

let host: HTMLElement;

function mount(stamp?: { version: string; hash: string; date: string }): HTMLElement {
  host = document.createElement("p");
  document.body.appendChild(host);
  if (stamp) mountBuildStamp(host, stamp);
  else mountBuildStamp(host);
  return host;
}

const RELEASED = { version: "0.20", hash: "3b83fcb", date: "2026-08-21" };

describe("the build stamp is a build-time constant, not a runtime question", () => {
  it("is injected by the config, so no request has to be made for it", () => {
    // A version the rail fetches is a version the rail cannot show while the API is down —
    // which is exactly when the reader wants to know what they are looking at.
    const injected = JSON.parse(define["__GW_BUILD__"] ?? "null") as {
      version: string;
      hash: string;
      date: string;
    };

    expect(injected.hash).toMatch(/^(dev|[0-9a-f]{7,40}\+?)$/);
    expect(injected.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    // Not a second copy of the odometer grammar: the injected version has to survive
    // stamp.ts's own validation, which is the only copy the bundle ever consults.
    expect(readStamp(injected).version).toBe(injected.version);
  });

  it("says dev rather than nothing when there was no git and no VERSION to ask", () => {
    // A release archive is not a checkout. An empty corner reads as a broken rail; `dev` reads
    // as what it is.
    expect(readStamp(undefined)).toEqual({ version: DEV_VERSION, hash: "dev", date: "" });
    expect(readStamp("3b83fcb")).toEqual({ version: DEV_VERSION, hash: "dev", date: "" });
  });

  it("refuses a hash that is not one, so a broken define cannot paint prose in the corner", () => {
    expect(readStamp({ hash: "not a hash", date: "2026-08-21" }).hash).toBe("dev");
    expect(readStamp({ hash: "", date: "2026-08-21" }).hash).toBe("dev");
  });

  it("refuses a version outside the odometer grammar rather than linking to a dead anchor", () => {
    // `0.2.0` is semver and this project does not cut semver; `0.1` and `1.100` are not
    // odometer readings either. Any of them would anchor at a heading that does not exist.
    for (const version of ["0.2.0", "0.1", "1.100", "v0.20", "latest", ""]) {
      expect(readStamp({ version, hash: "3b83fcb", date: "" }).version).toBe(DEV_VERSION);
    }
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
  it("reads v<version>+<hash> and keeps the detail in the tooltip", () => {
    mount(RELEASED);

    expect(host.querySelector(".gw-build-hash")?.textContent).toBe("v0.20+3b83fcb");
    expect(host.textContent).toBe("v0.20+3b83fcb");
    expect(host.title).toBe(
      "build v0.20+3b83fcb · built 2026-08-21 · what shipped in v0.20",
    );
  });

  it("drops the eyebrow once the value names itself, so the 132 px column still fits", () => {
    // `build` earned its width when the value was a bare hash. `v0.20+3b83fcb` does not need
    // the word, and the read column is a fixed column, not a growing one (gate-v BLOCKER-1).
    mount(RELEASED);

    expect(host.querySelector(".gw-build-label")).toBeNull();
  });

  it("links to the version's own heading, and the anchor is the rendered version exactly", () => {
    mount(RELEASED);
    const link = host.querySelector("a.gw-build-hash");
    const rendered = link?.textContent ?? "";

    expect(link?.getAttribute("href")).toBe("/changelog/#v0.20");
    // The one that matters: what the reader sees and where the click lands cannot disagree,
    // or the page scrolls to nothing and the release notes look empty.
    expect(link?.getAttribute("href")).toBe(`/changelog/#${rendered.split("+")[0]}`);
  });

  it("stays same-origin and out of the glossary", () => {
    mount(RELEASED);
    const link = host.querySelector("a.gw-build-hash");

    expect(link?.getAttribute("href")?.startsWith("/")).toBe(true);
    expect(link?.hasAttribute("data-no-glossary")).toBe(true);
    expect(link?.hasAttribute("target")).toBe(false);
  });

  it("says in the tooltip that the tree was dirty, since the hash alone cannot", () => {
    mount({ version: "0.20", hash: "3b83fcb+", date: "2026-08-21" });

    expect(host.textContent).toBe("v0.20+3b83fcb+");
    expect(host.title).toContain("uncommitted changes");
  });

  it("renders an unreleased build honestly: the old shape, and no fragment to nowhere", () => {
    mount({ version: DEV_VERSION, hash: "dev", date: "" });

    expect(host.textContent).toBe("build dev");
    expect(host.title).toBe("build dev");
    // The page exists; `#v0.0-dev` does not, and a link to it would scroll to nothing.
    expect(host.querySelector("a")?.getAttribute("href")).toBe("/changelog/");
  });

  it("is written once: a second mount replaces it rather than stacking a second hash", () => {
    mount(RELEASED);
    mountBuildStamp(host, { version: "0.21", hash: "aaaaaaa", date: "2026-08-22" });

    expect(host.querySelectorAll(".gw-build-hash")).toHaveLength(1);
    expect(host.textContent).toBe("v0.21+aaaaaaa");
  });

  it("renders the odometer's boundary readings without inventing a third digit", () => {
    // 0.99 rolls to 1.0 and the release after it is 1.01 — three headings, three anchors.
    for (const [version, anchor] of [
      ["0.99", "/changelog/#v0.99"],
      ["1.0", "/changelog/#v1.0"],
      ["1.01", "/changelog/#v1.01"],
      ["1.10", "/changelog/#v1.10"],
    ] as const) {
      const stamp = { version, hash: "3b83fcb", date: "" };
      expect(stampText(stamp)).toBe(`v${version}+3b83fcb`);
      expect(changelogHref(stamp)).toBe(anchor);
    }
    // 1.01 and 1.10 are different releases and must not collapse onto one anchor.
    expect(changelogHref({ version: "1.01", hash: "a", date: "" })).not.toBe(
      changelogHref({ version: "1.10", hash: "a", date: "" }),
    );
  });
});
