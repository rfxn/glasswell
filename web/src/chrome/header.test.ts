// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HEADER_IDS, setSignedIn, wireHeader } from "./header.ts";
import { setStatus, setVintage } from "./status.ts";

// vitest roots at web/, and happy-dom gives import.meta.url an http scheme.
const INDEX = readFileSync("index.html", "utf8");
const MARKUP = /<header id="gw-header"[\s\S]*?<\/header>/.exec(INDEX)?.[0] ?? "";

const onSignIn = vi.fn();
const onLogout = vi.fn();
let search: HTMLElement;

function element(id: string): HTMLElement {
  return document.getElementById(id) as HTMLElement;
}

beforeEach(() => {
  window.localStorage.clear();
  document.body.innerHTML = `${MARKUP}<div id="gw-toasts"></div>`;
  onSignIn.mockClear();
  onLogout.mockClear();
  search = document.createElement("div");
  const input = document.createElement("input");
  input.className = "gw-search-input";
  search.appendChild(input);
  wireHeader({ search, onSignIn, onLogout });
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("the header is a control surface, not a paragraph", () => {
  it("carries every id the wiring depends on", () => {
    // Asserted against the shipped markup, not the wired DOM, so a renamed id fails here
    // rather than in a browser — and so a control the flag removes after wiring still counts.
    for (const id of HEADER_IDS) expect(MARKUP, id).toContain(`id="${id}"`);
  });

  it("sets the wordmark as live text, so it is legible at whatever size the rail gives it", () => {
    // VF-1: the 660x168 lockup SVG was drawn at height:32px, which put the wordmark at
    // roughly 10px and unreadable. Live text scales with the type tokens instead.
    const wordmark = document.querySelector(".gw-wordmark");

    expect(wordmark?.textContent).toBe("glasswell");
    expect(wordmark?.querySelector(".gw-wordmark-well")?.textContent).toBe("well");
    expect(document.querySelector(".gw-lockup")).toBeNull();
  });

  it("keeps the mark as the rail's only image, labelled once by the link around it", () => {
    const images = [...document.querySelectorAll("img")];

    expect(images.map((image) => image.getAttribute("src"))).toEqual([
      "/brand/logo-mark-small.svg",
    ]);
    expect(images[0]?.getAttribute("alt")).toBe("");
    expect(document.querySelector(".gw-brand")?.getAttribute("aria-label")).toContain("glasswell");
  });

  it("keeps the strap to a micro-line and moves the sentence into Help", () => {
    const strap = document.querySelector(".gw-strap") as HTMLElement;

    expect(strap.textContent?.trim().split(/\s+/)).toHaveLength(3);
    expect(strap.title).toContain("checksummed regulator file");
    expect(element("gw-help-panel").textContent).toContain("derivation");
  });

  it("states the two-basin boundary without claiming Texas production", () => {
    const help = (element("gw-help-panel").textContent ?? "").replace(/\s+/g, " ");

    expect(help).toContain("North Dakota wells and production");
    expect(help).toContain("Texas wells and bore geometry");
    expect(help).toContain("completion events separate from regulator pool-to-formation mappings");
    expect(help).toContain("design measurements and formation tops remain explicitly unserved");
    expect(help).toContain("pending allocation");
    expect(help).toContain("Forecasts are not live");
    expect(help).toContain("completion anchors");
    expect(help).toContain("without a spud fallback");
    expect(help).toContain("17,563 of 43,817");
    expect(help).toContain("fv2.0");
    expect(help).toContain("82-day median source lag");
    expect(help).toContain("mdv1.4");
    expect(help).toContain("105,378 three-stream");
    expect(help).toContain("eight shared rolling splits");
    expect(help).toContain("tcv1.0");
    expect(help).toContain("Source-matched historical formation context is repaired");
    expect(help).toContain("without cross-manifest inference");
    expect(help).toContain("Missing lateral context remains explicitly unavailable");
    expect(help).toContain("accepted 2026-08-28 publication");
    expect(help).toContain("230 of 21,300 TEST instances");
    expect(help).toContain("5% ceiling");
    expect(help).toContain("not widened");
    expect(help).not.toContain("12.9484%");
  });

  it("mounts the search box into the header's control cluster", () => {
    expect(element("gw-search-slot").querySelector("input")).toBeTruthy();
  });

  it("composes the right cluster as find, then act, then read — one rhythm, three groups", () => {
    // VF-3: the cluster read as bolted-on because search, a chip, a button and two lines of
    // metadata sat in one undifferentiated flex row.
    const groups = [...document.querySelectorAll(".gw-controls > .gw-tools")];

    expect(groups.map((group) => group.className.split(/\s+/)[1])).toEqual([
      "gw-tools-find",
      "gw-tools-act",
      "gw-meta",
    ]);
  });

  it("gives the read column the two facts that never change width, and nothing else", () => {
    // Owner observation 3: search and help sat left of a 340 px column, and 254 px of that
    // column was a status line. The column now carries two fixed-format strings, so the tools
    // beside it start further right and stay there.
    const meta = document.querySelector(".gw-meta") as HTMLElement;

    expect(meta.querySelector("#gw-asof")).toBeTruthy();
    expect(meta.querySelector("#gw-build")).toBeTruthy();
    expect(meta.querySelector("#gw-status")).toBeNull();
    expect(meta.querySelector("#gw-key-btn")).toBeNull();
  });

  it("puts the signal readout in the rail's free space, ahead of the control cluster", () => {
    // gate-v BLOCKER-1 restated for the new layout: whatever the status says, it grows into
    // slack the rail already had rather than into the space search and help stand in.
    const signal = document.querySelector("#gw-signal") as HTMLElement;

    expect(signal.parentElement?.id).toBe("gw-header");
    expect(signal.nextElementSibling?.classList.contains("gw-controls")).toBe(true);
    expect(signal.querySelector("#gw-status")).toBeTruthy();
    expect(signal.querySelector("#gw-key-btn")).toBeTruthy();
  });

  it("keeps search and help to the right of the status, where the reading eye ends", () => {
    const order = [...document.querySelectorAll("#gw-status, .gw-search-input, #gw-help-btn")];

    expect(order.map((element) => element.id || element.className)).toEqual([
      "gw-status",
      "gw-search-input",
      "gw-help-btn",
    ]);
  });
});

describe("the build stamp (owner observation 1)", () => {
  it("stands beside as_of in the corner the owner is pointing at", () => {
    const build = element("gw-build");

    expect(build.closest(".gw-meta")).toBeTruthy();
    expect(build.previousElementSibling?.id).toBe("gw-asof");
    // The stamp grammar moved from `build <hash>` to the release literal `v<M.NN>+<hash>`
    // when the odometer landed; `dev` survives as the no-git fallback (stamp.test.ts owns
    // the grammar's own coverage — this only pins placement plus a sane reading).
    expect(build.textContent).toMatch(/^(v\d+\.\d{1,2}\+[0-9a-f]{7,40}\+?|dev)$/);
  });

  it("leaves the vintage slot reading as_of <date>, which is what reads it", () => {
    // The stamp is its own element on purpose: setVintage owns #gw-asof's children, and a
    // second writer in that slot is the four-channel rule with a new coat of paint.
    setVintage("2026-08-20");

    expect(element("gw-asof").textContent).toBe("as_of 2026-08-20");
    expect(element("gw-asof").querySelector(".gw-build-hash")).toBeNull();
  });

  it("never reaches the status channel, because a build is not a status", () => {
    expect(element("gw-status").textContent).toBe("");
  });

  it("is repeated in Help, which is the corner at the width the corner does not exist", () => {
    setVintage("2026-08-20");

    expect(element("gw-help-build").textContent).toBe(element("gw-build").textContent);
    expect(element("gw-help-asof").textContent).toBe("as_of 2026-08-20");
    expect(element("gw-help-asof").querySelector("time")?.dateTime).toBe("2026-08-20");
  });

  it("keeps one writer for the vintage, so the two places cannot disagree", () => {
    setVintage("2026-08-20");
    setVintage(null);

    expect(element("gw-asof").textContent).toBe("as_of —");
    expect(element("gw-help-asof").textContent).toBe("as_of —");
  });
});

describe("the ⌾ hint", () => {
  it("ships hidden, so a reader who has already learned it never sees it", () => {
    expect(element("gw-hint").hidden).toBe(true);
    expect(/<div\s+id="gw-hint"([^>]*)>/.exec(MARKUP)?.[1]).toMatch(/\bhidden\b/);
  });

  it("lives with the control that documents ⌾ permanently, not in the read column", () => {
    expect(element("gw-hint").closest(".gw-tools-act")).toBeTruthy();
    expect(element("gw-help-panel").textContent).toContain("⌾");
  });

  it("appears when the frozen call site sets the sentence, and takes no focus", () => {
    const input = element("gw-search-slot").querySelector("input") as HTMLInputElement;
    input.focus();

    setStatus("Click any ⌾ to see where a number came from.");

    expect(element("gw-hint").hidden).toBe(false);
    expect(element("gw-hint").textContent).toContain("Click any ⌾");
    expect(element("gw-status").textContent).toBe("");
    expect(document.activeElement).toBe(input);
  });
});

describe("the theme control", () => {
  it("is not in the shipped rail at all, because the flag defaults off", () => {
    // gate-v BLOCKER-2: reachable and broken over an unthemed map. wireHeader still wires it,
    // so the day Track M lands basemap theming the flag is the only thing that moves.
    expect(element("gw-theme-btn")).toBeNull();
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("ships hidden, so the flag-off build never paints it before the wiring runs", () => {
    // gate-v m-3: the module script is deferred, so an unhidden button is painted and inert
    // for the pre-hydration window and then vanishes. The flag-on branch unhides it.
    const attributes = /<button\s+id="gw-theme-btn"([^>]*)>/.exec(MARKUP)?.[1] ?? "";

    expect(attributes).toMatch(/\bhidden\b/);
  });

  describe("with the flag on", () => {
    beforeEach(() => {
      vi.stubEnv("VITE_GW_THEME_TOGGLE", "1");
      document.body.innerHTML = `${MARKUP}<div id="gw-toasts"></div>`;
      wireHeader({ search, onSignIn, onLogout });
    });

    it("lives in the action group and starts on the brand default", () => {
      expect(element("gw-theme-btn").closest(".gw-tools-act")).toBeTruthy();
      expect(document.documentElement.dataset.theme).toBe("dark");
    });

    it("is unhidden by the wiring, since the markup ships it hidden", () => {
      expect(element("gw-theme-btn").hidden).toBe(false);
    });

    it("flips the document theme when clicked", () => {
      element("gw-theme-btn").click();

      expect(document.documentElement.dataset.theme).toBe("light");
    });
  });
});

describe("the help disclosure", () => {
  it("opens and closes, keeping aria-expanded truthful", () => {
    const button = element("gw-help-btn");

    button.click();
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(element("gw-help-panel").hidden).toBe(false);

    button.click();
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(element("gw-help-panel").hidden).toBe(true);
  });

  it("closes on Escape and hands focus back to the button", () => {
    const button = element("gw-help-btn");
    button.click();

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    expect(element("gw-help-panel").hidden).toBe(true);
    expect(document.activeElement).toBe(button);
  });

  it("closes when a click lands outside it", () => {
    element("gw-help-btn").click();

    document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));

    expect(element("gw-help-panel").hidden).toBe(true);
  });
});

describe("the session chip", () => {
  it("starts hidden, because a live session is not news", () => {
    expect(element("gw-key-btn").hidden).toBe(true);
  });

  it("opens the login panel once a refused request makes it visible", () => {
    const chip = element("gw-key-btn");
    chip.hidden = false;

    chip.click();

    expect(onSignIn).toHaveBeenCalledOnce();
  });
});

describe("the sign-out control", () => {
  it("ships hidden, so a signed-out reader is never offered it", () => {
    expect(element("gw-logout-btn").hidden).toBe(true);
    expect(/<button\s+id="gw-logout-btn"([^>]*)>/.exec(MARKUP)?.[1]).toMatch(/\bhidden\b/);
  });

  it("lives in the action group, beside the other controls that never change width", () => {
    expect(element("gw-logout-btn").closest(".gw-tools-act")).toBeTruthy();
  });

  it("appears once a session is known, and names the account it would end", () => {
    setSignedIn("ryan");

    expect(element("gw-logout-btn").hidden).toBe(false);
    expect(element("gw-logout-btn").title).toContain("ryan");
  });

  it("goes away again when there is no session to end", () => {
    setSignedIn("ryan");

    setSignedIn(null);

    expect(element("gw-logout-btn").hidden).toBe(true);
    expect(element("gw-logout-btn").title).toBe("");
  });

  it("hands the press to the caller rather than ending the session itself", () => {
    setSignedIn("ryan");

    element("gw-logout-btn").click();

    expect(onLogout).toHaveBeenCalledOnce();
    expect(onSignIn).not.toHaveBeenCalled();
  });
});

describe("the mode switch (SB-08 §2.1)", () => {
  function modes(): HTMLButtonElement[] {
    return [...element("gw-mode-switch").querySelectorAll("button")] as HTMLButtonElement[];
  }

  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    document.body.innerHTML = `${MARKUP}<div id="gw-toasts"></div>`;
    wireHeader({ search, onSignIn, onLogout });
  });

  it("offers the three surfaces as one group, between the brand and the controls", () => {
    expect(modes().map((button) => button.dataset["view"])).toEqual(["map", "explore", "status"]);
    expect(element("gw-mode-switch").getAttribute("role")).toBe("group");
    expect(element("gw-mode-switch").previousElementSibling?.classList.contains("gw-brand")).toBe(true);
  });

  it("presses the surface the URL is on, so a deep link arrives with the switch already right", () => {
    window.history.replaceState(null, "", "/?view=explore&ds=wells");
    document.body.innerHTML = `${MARKUP}<div id="gw-toasts"></div>`;
    wireHeader({ search, onSignIn, onLogout });

    expect(modes().map((button) => button.getAttribute("aria-pressed"))).toEqual([
      "false",
      "true",
      "false",
    ]);
  });

  it("crosses with a pushState, so the back button returns the reader to where they were", () => {
    const before = window.history.length;

    modes()[1]?.click();

    expect(new URLSearchParams(window.location.search).get("view")).toBe("explore");
    expect(window.history.length).toBeGreaterThan(before);
  });

  it("carries as_of across the crossing — the surfaces may not disagree about a number", () => {
    window.history.replaceState(null, "", "/?as_of=2026-08-01");
    document.body.innerHTML = `${MARKUP}<div id="gw-toasts"></div>`;
    wireHeader({ search, onSignIn, onLogout });

    modes()[1]?.click();

    expect(new URLSearchParams(window.location.search).get("as_of")).toBe("2026-08-01");
  });

  it("follows the back button rather than staying pressed on the surface it left", () => {
    modes()[1]?.click();
    window.history.replaceState(null, "", "/");
    window.dispatchEvent(new PopStateEvent("popstate"));

    expect(modes().map((button) => button.getAttribute("aria-pressed"))).toEqual([
      "true",
      "false",
      "false",
    ]);
  });

  it("does nothing when the reader presses the surface they are already on", () => {
    const url = window.location.href;

    modes()[0]?.click();

    expect(window.location.href).toBe(url);
  });

  it("deep-links Status and clears map overlays without dropping route context", () => {
    window.history.replaceState(
      null,
      "",
      "/?well=3305310451&explain=drv_1&as_of=2026-08-01&f.q=bakken",
    );
    document.body.innerHTML = `${MARKUP}<div id="gw-toasts"></div>`;
    wireHeader({ search, onSignIn, onLogout });

    modes()[2]?.click();

    const params = new URLSearchParams(window.location.search);
    expect(params.get("view")).toBe("status");
    expect(params.has("well")).toBe(false);
    expect(params.has("explain")).toBe(false);
    expect(params.get("as_of")).toBe("2026-08-01");
    expect(params.get("f.q")).toBe("bakken");
  });
});
