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

const BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
const CSRF_HEADER = "X-Glasswell-CSRF";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);
/** The owner-key era's storage slot, cleared at boot so no surviving path can send one. */
const LEGACY_KEY_STORAGE = "glasswell.key";

let csrf: string | null = null;

export interface Challenge {
  csrf_token: string;
  expires_in: number;
}

export interface Session {
  username: string | null;
  role: string;
  kind: string;
  expires_at: string | null;
  absolute_expires_at: string | null;
}

export function purgeLegacyKey(): void {
  window.localStorage.removeItem(LEGACY_KEY_STORAGE);
}

/** The session rides an HttpOnly cookie; only a write carries the token that proves origin. */
export function authHeaders(method = "GET"): Record<string, string> {
  if (SAFE_METHODS.has(method.toUpperCase())) return {};
  return csrf === null ? {} : { [CSRF_HEADER]: csrf };
}

export function apiUrl(path: string, query: Record<string, string | string[]> = {}): string {
  const url = new URL(`${BASE}${path}`, window.location.origin);
  for (const [name, value] of Object.entries(query)) {
    for (const item of Array.isArray(value) ? value : [value]) url.searchParams.append(name, item);
  }
  return url.pathname + url.search;
}

export interface ResponseMeta {
  status: number;
  headers: Headers;
  elapsed_ms: number;
}

export async function getEnvelope<T>(
  path: string,
  query: Record<string, string | string[]> = {},
  signal?: AbortSignal,
  meta?: { out?: ResponseMeta },
): Promise<Envelope<T>> {
  const started = performance.now();
  const response = await fetch(apiUrl(path, query), {
    headers: { Accept: "application/json", ...authHeaders() },
    credentials: "same-origin",
    signal,
  });
  // Before the throw: a failed request keeps its REQUEST block, so it keeps its status and
  // its timing too (SB-08 §4.7).
  if (meta) {
    meta.out = {
      status: response.status,
      headers: response.headers,
      elapsed_ms: performance.now() - started,
    };
  }
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

export async function getChallenge(): Promise<Challenge> {
  const challenge = (await getEnvelope<Challenge>("/v1/session/challenge")).data;
  csrf = challenge.csrf_token;
  return challenge;
}

export async function whoami(): Promise<Session> {
  return (await getEnvelope<Session>("/v1/session")).data;
}

export async function login(username: string, password: string): Promise<Session> {
  const session = await mutate<Session>("POST", "/v1/session", { username, password });
  // Login deletes the pre-session cookie the held token was bound to, so that token is spent.
  csrf = null;
  return session;
}

export async function logout(): Promise<Session> {
  const ended = await mutate<Session>("DELETE", "/v1/session");
  csrf = null;
  return ended;
}

async function mutate<T>(method: string, path: string, body?: unknown): Promise<T> {
  try {
    return await send<T>(method, path, body);
  } catch (error) {
    // A token lapses four hours in and the session behind it usually has not, so one
    // re-challenge separates a stale token from a refusal the reader has to act on.
    if (!(error instanceof ApiError) || error.code !== "forbidden") throw error;
    csrf = null;
    return send<T>(method, path, body);
  }
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  if (csrf === null) await getChallenge();
  const headers: Record<string, string> = { Accept: "application/json", ...authHeaders(method) };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(apiUrl(path), {
    method,
    headers,
    credentials: "same-origin",
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) throw new ApiError(await problemOf(response));
  return ((await response.json()) as Envelope<T>).data;
}

export function tileUrl(layer: string): string {
  return `${BASE}/v1/tiles/${layer}/{z}/{x}/{y}.pbf`;
}
