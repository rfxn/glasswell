import type { Envelope } from "./envelope.ts";

export interface Problem {
  type: string;
  title: string;
  status: number;
  instance?: string;
  request_id?: string;
  detail?: string;
  errors?: { pointer?: string; code?: string; detail?: string }[];
  handle?: string;
  last_resolved?: string | null;
  stop_reason?: string | null;
}

export class ApiError extends Error {
  readonly problem: Problem;

  constructor(problem: Problem) {
    super(problem.detail ?? problem.title);
    this.name = "ApiError";
    this.problem = problem;
  }

  get code(): string {
    return this.problem.type.split("/").pop() ?? "unknown";
  }
}

const KEY_STORAGE = "glasswell.key";
const KEY_PARAM = "key";
const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

/**
 * `#key=` once, then localStorage; a build-time key is the fallback for a kiosk build.
 * The fragment, never the query string: a query string reaches the server's access log.
 */
export function apiKey(): string | null {
  const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const fromUrl = fragment.get(KEY_PARAM);
  if (fromUrl) {
    window.localStorage.setItem(KEY_STORAGE, fromUrl);
    fragment.delete(KEY_PARAM);
    const url = new URL(window.location.href);
    url.hash = fragment.toString();
    window.history.replaceState(null, "", url.toString());
    return fromUrl;
  }
  return window.localStorage.getItem(KEY_STORAGE) ?? import.meta.env.VITE_GLASSWELL_KEY ?? null;
}

export function authHeaders(): Record<string, string> {
  const key = apiKey();
  return key ? { "X-Glasswell-Key": key } : {};
}

export function apiUrl(path: string, query: Record<string, string | string[]> = {}): string {
  const url = new URL(`${BASE}${path}`, window.location.origin);
  for (const [name, value] of Object.entries(query)) {
    for (const item of Array.isArray(value) ? value : [value]) url.searchParams.append(name, item);
  }
  return url.pathname + url.search;
}

export async function getEnvelope<T>(
  path: string,
  query: Record<string, string | string[]> = {},
  signal?: AbortSignal,
): Promise<Envelope<T>> {
  const response = await fetch(apiUrl(path, query), {
    headers: { Accept: "application/json", ...authHeaders() },
    signal,
  });
  if (!response.ok) throw new ApiError(await problemOf(response));
  return (await response.json()) as Envelope<T>;
}

async function problemOf(response: Response): Promise<Problem> {
  try {
    const body = (await response.json()) as Partial<Problem>;
    return {
      type: body.type ?? "about:blank",
      title: body.title ?? response.statusText,
      status: body.status ?? response.status,
      ...body,
    } as Problem;
  } catch {
    // A non-JSON body (a proxy error page, say) still has to render as a problem.
    return { type: "about:blank", title: response.statusText, status: response.status };
  }
}

export function tileUrl(layer: string): string {
  return `${BASE}/v1/tiles/${layer}/{z}/{x}/{y}.pbf`;
}
