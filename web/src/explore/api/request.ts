import { apiUrl } from "../../api/client.ts";

/**
 * SB-08 §4.2: the reader's own key, never the page's. Every copy target — a chat window, an
 * issue, a notebook — is a credential-leak path, so the key this module renders is a name.
 */
export const KEY_PLACEHOLDER = "$GLASSWELL_KEY";
// The browser now holds a session cookie, but a copied snippet runs outside the browser: the
// machine path is still the API key, so these snippets keep naming its header.
const KEY_HEADER = "X-Glasswell-Key";
const ACCEPT = "application/json";

/** What `router.requestFor` returns, structurally. Building from it is what makes drift impossible. */
export interface IssuedRequest {
  operationId: string;
  path: string;
  query: Record<string, string[]>;
}

export const DIALECTS = ["curl", "httpie", "fetch"] as const;
export type Dialect = (typeof DIALECTS)[number];

/** The one URL builder: `apiUrl` (client.ts:75) is the function the grid fetched through. */
export function absoluteUrl(request: { path: string; query?: Record<string, string[]> }): string {
  return new URL(apiUrl(request.path, request.query ?? {}), window.location.origin).toString();
}

export function commandFor(request: IssuedRequest, dialect: Dialect): string {
  const url = absoluteUrl(request);
  if (dialect === "httpie") {
    return [
      `http GET '${url}' \\`,
      `  '${KEY_HEADER}:${KEY_PLACEHOLDER}' \\`,
      `  'Accept:${ACCEPT}'`,
    ].join("\n");
  }
  if (dialect === "fetch") {
    return [
      `const response = await fetch("${url}", {`,
      `  headers: { "${KEY_HEADER}": "${KEY_PLACEHOLDER}", Accept: "${ACCEPT}" },`,
      "});",
      "const envelope = await response.json();",
    ].join("\n");
  }
  return [
    "curl -s \\",
    `  -H "${KEY_HEADER}: ${KEY_PLACEHOLDER}" \\`,
    `  -H "Accept: ${ACCEPT}" \\`,
    `  '${url}'`,
  ].join("\n");
}

/**
 * The server built the next URL, so the cursor is read out of it rather than assembled here —
 * the same discipline `grid.ts:followNext` applies, and the reason the walk snippet below
 * follows `links.next` instead of incrementing anything.
 */
export function requestFrom(operationId: string, href: string): IssuedRequest | null {
  const [path, search = ""] = href.split("?");
  if (!path) return null;
  const query: Record<string, string[]> = {};
  for (const [name, value] of new URLSearchParams(search)) (query[name] ??= []).push(value);
  return { operationId, path, query };
}

/** §4.2: a page is copyable on its own; the whole collection is a loop that follows a link. */
export function walkAllPages(request: IssuedRequest): string {
  return [
    `next='${absoluteUrl(request)}'`,
    'while [ -n "$next" ]; do',
    `  page=$(curl -s -H "${KEY_HEADER}: ${KEY_PLACEHOLDER}" "$next")`,
    `  printf '%s\\n' "$page"`,
    `  next=$(printf '%s' "$page" | jq -r '.links.next | strings')`,
    `  [ -n "$next" ] && next="${window.location.origin}$next"`,
    "done",
  ].join("\n");
}

export interface StepLike {
  operationId: string;
  request: { path: string; query: Record<string, string[]> };
  title?: string;
}

/** The breadcrumb's command and the pane's are the same command; C8's placeholder lives here now. */
export function curlFor(step: StepLike): string {
  return commandFor({ operationId: step.operationId, ...step.request }, "curl");
}

export function curlList(walked: readonly StepLike[]): string {
  return walked
    .map((step, index) => `# ${index + 1}. ${step.title ?? step.operationId}\n${curlFor(step)}`)
    .join("\n");
}
