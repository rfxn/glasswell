/**
 * Which bundle this is, and what shipped in it. Injected by `vite.config.ts` at build time
 * rather than fetched, so the rail can still answer the question while the API cannot —
 * which is when it is asked. Static text in its own element, written at mount and never
 * through the status channel (chrome/status.ts owns that one).
 */
import "./stamp.css";

declare const __GW_BUILD__: unknown;

export interface BuildStamp {
  version: string;
  hash: string;
  date: string;
}

/** No SPA fallback exists (DR-57), so this is a real directory with a real index.html. */
export const CHANGELOG_PATH = "/changelog/";
/** What a tree with no `VERSION` file honestly is: something no release was cut from. */
export const DEV_VERSION = "0.0-dev";

const UNKNOWN: BuildStamp = { version: DEV_VERSION, hash: "dev", date: "" };
// The odometer, not semver: `X.0`, then `X.01`..`X.09`, then `X.10`..`X.99`. RELEASING.md.
const VERSION = /^(?:0|[1-9][0-9]*)\.(?:0|0[1-9]|[1-9][0-9])$/;
// `+` is the dirty marker vite.config.ts appends; a stamp that rounds to the commit is a lie.
const HASH = /^[0-9a-f]{7,40}\+?$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;

export function readStamp(injected: unknown): BuildStamp {
  if (typeof injected !== "object" || injected === null) return UNKNOWN;
  const { version, hash, date } = injected as {
    version?: unknown;
    hash?: unknown;
    date?: unknown;
  };
  return {
    version: typeof version === "string" && VERSION.test(version) ? version : UNKNOWN.version,
    hash: typeof hash === "string" && HASH.test(hash) ? hash : UNKNOWN.hash,
    date: typeof date === "string" && DATE.test(date) ? date : "",
  };
}

export function buildStamp(): BuildStamp {
  return readStamp(typeof __GW_BUILD__ === "undefined" ? undefined : __GW_BUILD__);
}

/** `v0.20+3b83fcb`: the release, then the commit inside it, in build-metadata order. */
export function stampText(stamp: BuildStamp): string {
  return stamp.version === DEV_VERSION ? stamp.hash : `v${stamp.version}+${stamp.hash}`;
}

/** The fragment is the version exactly as rendered, because that is the heading's id. */
export function changelogHref(stamp: BuildStamp): string {
  return stamp.version === DEV_VERSION ? CHANGELOG_PATH : `${CHANGELOG_PATH}#v${stamp.version}`;
}

export function mountBuildStamp(host: HTMLElement, stamp: BuildStamp = buildStamp()): void {
  const parts: Node[] = [];
  if (stamp.version === DEV_VERSION) {
    // The eyebrow earns its share of a 132 px column only when the value cannot name itself.
    // `v0.20+3b83fcb` can; a bare hash cannot, so the unversioned build keeps the word.
    const label = document.createElement("span");
    label.className = "gw-build-label";
    label.setAttribute("data-no-glossary", "");
    label.textContent = "build";
    parts.push(label, document.createTextNode(" "));
  }
  const link = document.createElement("a");
  link.className = "gw-build-hash";
  link.setAttribute("data-no-glossary", "");
  link.setAttribute("href", changelogHref(stamp));
  link.textContent = stampText(stamp);
  parts.push(link);
  host.replaceChildren(...parts);
  host.title = [
    `build ${stampText(stamp)}`,
    stamp.date ? `built ${stamp.date}` : "",
    stamp.hash.endsWith("+") ? "uncommitted changes" : "",
    stamp.version === DEV_VERSION ? "" : `what shipped in v${stamp.version}`,
  ]
    .filter(Boolean)
    .join(" · ");
}
