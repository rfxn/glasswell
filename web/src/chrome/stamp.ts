/**
 * Which bundle this is. Injected by `vite.config.ts` at build time rather than fetched, so
 * the rail can still answer the question while the API cannot — which is when it is asked.
 * Static text: it is written into its own element at mount and never through the status
 * channel (chrome/status.ts owns that one).
 */
declare const __GW_BUILD__: unknown;

export interface BuildStamp {
  hash: string;
  date: string;
}

const UNKNOWN: BuildStamp = { hash: "dev", date: "" };
// `+` is the dirty marker vite.config.ts appends; a stamp that rounds to the commit is a lie.
const HASH = /^[0-9a-f]{7,40}\+?$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;

export function readStamp(injected: unknown): BuildStamp {
  if (typeof injected !== "object" || injected === null) return UNKNOWN;
  const { hash, date } = injected as { hash?: unknown; date?: unknown };
  return {
    hash: typeof hash === "string" && HASH.test(hash) ? hash : UNKNOWN.hash,
    date: typeof date === "string" && DATE.test(date) ? date : "",
  };
}

export function buildStamp(): BuildStamp {
  return readStamp(typeof __GW_BUILD__ === "undefined" ? undefined : __GW_BUILD__);
}

export function mountBuildStamp(host: HTMLElement, stamp: BuildStamp = buildStamp()): void {
  const label = document.createElement("span");
  label.className = "gw-build-label";
  label.setAttribute("data-no-glossary", "");
  label.textContent = "build";
  const hash = document.createElement("span");
  hash.className = "gw-build-hash";
  hash.setAttribute("data-no-glossary", "");
  hash.textContent = stamp.hash;
  host.replaceChildren(label, document.createTextNode(" "), hash);
  host.title = [
    `build ${stamp.hash}`,
    stamp.date ? `built ${stamp.date}` : "",
    stamp.hash.endsWith("+") ? "uncommitted changes" : "",
  ]
    .filter(Boolean)
    .join(" · ");
}
