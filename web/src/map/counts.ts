import type { Envelope, Figure, Links } from "../api/envelope.ts";
import { UNMAPPED_STATUS } from "./status.ts";

export const STATUS_SUMMARY_PATH = "/v1/wells/status-summary";

/** How long a settle waits before the counts are called unavailable. A whole-world box was
 *  measured at 1.4 s over 399,280 points; ten seconds is a failure, not a slow answer. */
const DEFAULT_TIMEOUT_MS = 10_000;

/** `[minLon, minLat, maxLon, maxLat]`, WGS84 — the order `?bbox=` takes. */
export type Bbox = readonly [number, number, number, number];

export interface StatusCount {
  status: string;
  wells: Figure;
}

export interface BasinStatusCounts {
  basin: string | null;
  state_code: string | null;
  status_vocabulary_rule: string | null;
  wells: Figure;
  unmapped_wells: Figure | null;
  statuses: StatusCount[];
}

export interface WellStatusSummary {
  bbox: string;
  wells: Figure | null;
  unmapped_wells: Figure | null;
  statuses: StatusCount[];
  basins: BasinStatusCounts[];
  vocabulary_rules: string[];
}

export interface VocabularyLink {
  rule: string;
  href: string | null;
}

export interface CountsLoading {
  kind: "loading";
  bbox: Bbox;
}

/**
 * `links.explain` and `meta.warnings` are deliberately not carried. The prebuilt explain call
 * is capped at 20 handles and says so in a warning, while every count already resolves through
 * its own `d` — one truncated link is a worse affordance than ten complete ones. The warnings
 * that a map key would want (`geometry_without_a_well_row`) sit beside two that describe the
 * response's own construction (`explain_link_truncated`, `aggregate_spans_derivations`), and
 * putting those on the canvas would be noise; selecting between them is its own decision.
 */
export interface CountsReady {
  kind: "ready";
  bbox: Bbox;
  counts: Record<string, number>;
  handles: Record<string, string>;
  total: number | null;
  totalHandle: string | null;
  vocabulary: VocabularyLink[];
  /**
   * The vintage this answer resolved to. The map has no other reading of it — the rail's chip
   * is written by main.ts — and a crossing off this surface pins it so the link a reader
   * shares reproduces the numbers they were looking at (SB-08 M6).
   */
  resolved: string | null;
}

export interface CountsError {
  kind: "error";
  bbox: Bbox;
  message: string;
}

export type CountsState = CountsLoading | CountsReady | CountsError;

export interface CountSourceOptions {
  load(bbox: Bbox, signal: AbortSignal): Promise<Envelope<WellStatusSummary>>;
  onState(state: CountsState): void;
  timeoutMs?: number;
}

export interface CountSource {
  request(bbox: Bbox): void;
}

/**
 * The viewport as a box the API will accept. A viewport that reaches past the antimeridian
 * becomes the whole world rather than the slice `[-180, maxLon]`: `?bbox=` cannot express a
 * box that wraps, and clamping would drop wells the reader can see — the same defect this
 * module exists to remove, from the other end. It over-states only at the zooms where the
 * world is on screen anyway.
 */
export function normaliseBbox(box: Bbox): Bbox {
  const [minLon, minLat, maxLon, maxLat] = box;
  const wraps =
    minLon < -180 || maxLon > 180 || maxLon <= minLon || maxLon - minLon >= 360;
  return wraps
    ? [-180, clampLat(minLat), 180, clampLat(maxLat)]
    : [minLon, clampLat(minLat), maxLon, clampLat(maxLat)];
}

/** `String(n)` is the shortest string that round-trips to the same double, as `repr` is. */
export function bboxParam(box: Bbox): string {
  return box.map((value) => String(value)).join(",");
}

export function parseBbox(echo: string | null | undefined): Bbox | null {
  if (typeof echo !== "string") return null;
  const parts = echo.split(",");
  if (parts.length !== 4) return null;
  const numbers = parts.map((part) => (part.trim() === "" ? Number.NaN : Number(part)));
  if (numbers.some((value) => !Number.isFinite(value))) return null;
  return [numbers[0]!, numbers[1]!, numbers[2]!, numbers[3]!];
}

/**
 * By number, never by string: the echo is the *parsed* box rendered back, so `-104` returns
 * as `-104.0`. Exact, with no tolerance — the four floats are the ones the query ran with,
 * and two viewports a metre apart are two boxes (seam §2.3 rule 3).
 */
export function sameBbox(a: Bbox | null, b: Bbox | null): boolean {
  if (!a || !b) return false;
  return a.every((value, index) => value === b[index]);
}

/** Present classes only. A class the box does not hold has no count, which is not a zero. */
export function statusCounts(data: WellStatusSummary): Record<string, number> {
  const counts: Record<string, number> = Object.fromEntries(
    data.statuses.map((row) => [row.status, Number(row.wells.value)]),
  );
  if (data.unmapped_wells) counts[UNMAPPED_STATUS.id] = Number(data.unmapped_wells.value);
  return counts;
}

/** One handle per class, each addressing its own count rather than a neighbour's. */
export function statusHandles(data: WellStatusSummary): Record<string, string> {
  const handles: Record<string, string> = Object.fromEntries(
    data.statuses.map((row) => [row.status, row.wells.d]),
  );
  if (data.unmapped_wells) handles[UNMAPPED_STATUS.id] = data.unmapped_wells.d;
  return handles;
}

export interface DrawnCensus {
  wells: number;
  derivation: string | null;
}

/**
 * What the canvas drew, kept beside what the box holds so the pair can be read together.
 * Deduplicated by API-10: a point in a tile's buffer ring comes back once per tile carrying
 * it, and a doubled dot would put the drawn number above the box's own count.
 */
export function censusOfDrawn(
  features: readonly { properties?: Record<string, unknown> | null }[],
): DrawnCensus {
  const seen = new Set<string>();
  let anonymous = 0;
  let derivation: string | null = null;
  for (const feature of features) {
    const properties = feature.properties ?? {};
    const api10 = properties["api10"];
    if (typeof api10 === "string" && api10 !== "") seen.add(api10);
    else anonymous += 1;
    const build = properties["derivation_id"];
    if (derivation === null && typeof build === "string") derivation = build;
  }
  return { wells: seen.size + anonymous, derivation };
}

/** R8: the rules that shaped this answer, each with the row a reader can open, where served. */
export function vocabularyLinks(data: WellStatusSummary, links: Links): VocabularyLink[] {
  return data.vocabulary_rules.map((rule) => ({ rule, href: links[rule] ?? null }));
}

interface Attempt {
  token: number;
  bbox: Bbox;
  controller: AbortController;
  timer: ReturnType<typeof setTimeout>;
  settled: boolean;
}

/**
 * One question at a time, and only the current viewport's answer is ever published.
 *
 * Two independent guards, because they fail differently. The token catches an answer that is
 * merely late — the reader has panned on, and out-of-order completions are the normal case at
 * 250 ms settles. The echo catches an answer that is *wrong*: a body for a box nobody asked
 * about, which no amount of ordering would have caught, and which would paint a false count
 * under the reader's legend.
 */
export function createCountSource(options: CountSourceOptions): CountSource {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  let token = 0;
  let attempt: Attempt | null = null;
  let answered: CountsState | null = null;

  function publish(state: CountsState): void {
    answered = state;
    options.onState(state);
  }

  function settle(record: Attempt, state: CountsState): void {
    if (record.settled || record.token !== token) return;
    record.settled = true;
    clearTimeout(record.timer);
    attempt = null;
    publish(state);
  }

  async function run(record: Attempt): Promise<void> {
    try {
      const envelope = await options.load(record.bbox, record.controller.signal);
      if (!sameBbox(parseBbox(envelope.data.bbox), record.bbox)) {
        settle(record, {
          kind: "error",
          bbox: record.bbox,
          message: "the summary answered for a different viewport",
        });
        return;
      }
      settle(record, ready(record.bbox, envelope));
    } catch (error) {
      settle(record, { kind: "error", bbox: record.bbox, message: messageOf(error) });
    }
  }

  return {
    request(raw) {
      const bbox = normaliseBbox(raw);
      if (attempt) {
        if (sameBbox(attempt.bbox, bbox)) return;
        clearTimeout(attempt.timer);
        attempt.controller.abort();
      } else if (answered?.kind === "ready" && sameBbox(answered.bbox, bbox)) {
        return;
      }
      const controller = new AbortController();
      const record: Attempt = {
        token: ++token,
        bbox,
        controller,
        settled: false,
        // The deadline is the coordinator's, not the transport's: a `load` that never rejects
        // on abort would otherwise leave the legend loading for the rest of the session.
        timer: setTimeout(() => {
          controller.abort();
          settle(record, {
            kind: "error",
            bbox,
            message: "the counts took too long to answer",
          });
        }, timeoutMs),
      };
      attempt = record;
      publish({ kind: "loading", bbox });
      void run(record);
    },
  };
}

/**
 * The vintage a crossing off this surface pins, across a sequence of answers. A failure or a
 * request in flight does not un-resolve what is already on the canvas — the same tiles and the
 * same counts are still painted — so the last ready envelope's vintage stands until another
 * ready envelope replaces it. A ready envelope that resolved nothing replaces it with nothing:
 * pinning a vintage the current answer does not claim is the drift M6 is about, one step later.
 */
export function retainVintage(previous: string | null, state: CountsState): string | null {
  return state.kind === "ready" ? state.resolved : previous;
}

function ready(bbox: Bbox, envelope: Envelope<WellStatusSummary>): CountsReady {
  const data = envelope.data;
  return {
    kind: "ready",
    bbox,
    counts: statusCounts(data),
    handles: statusHandles(data),
    total: data.wells ? Number(data.wells.value) : null,
    totalHandle: data.wells?.d ?? null,
    vocabulary: vocabularyLinks(data, envelope.links),
    resolved: envelope.meta.as_of.resolved,
  };
}

function messageOf(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

function clampLat(value: number): number {
  return Math.min(90, Math.max(-90, value));
}
