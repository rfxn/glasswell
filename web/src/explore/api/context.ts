import type { ResponseMeta } from "../../api/client.ts";
import type { Envelope } from "../../api/envelope.ts";
import type { CatalogueDataset } from "../catalogue.ts";
import type { IssuedRequest } from "./request.ts";

/**
 * The pane has no route of its own (§2.2) and the row seam deliberately does not re-render
 * (C8 N3), so the call in view is published here rather than read back off the URL. The grid
 * publishes the collection it issued; the record published on top of it is what §4.1 means by
 * "the current state" while a row is open, and closing the row uncovers the collection again.
 */
export type CallState = "unissued" | "pending" | "loaded" | "failed";

export interface ApiCall {
  state: CallState;
  role: "collection" | "record";
  dataset: CatalogueDataset;
  request: IssuedRequest;
  /** The path parameters the reader has not supplied: nothing was issued until they are. */
  missing?: string[];
  envelope: Envelope<unknown> | null;
  error: unknown;
  meta: ResponseMeta | null;
}

type Listener = (call: ApiCall | null) => void;

let collection: ApiCall | null = null;
let record: ApiCall | null = null;
const listeners = new Set<Listener>();

export function publishCall(call: ApiCall): void {
  if (call.role === "record") record = call;
  else {
    collection = call;
    record = null;
  }
  announce();
}

/** A closed row is not a call that failed: the collection underneath it is still the answer. */
export function clearRecord(): void {
  if (record === null) return;
  record = null;
  announce();
}

export function currentCall(): ApiCall | null {
  return record ?? collection;
}

export function onCall(listener: Listener, signal: AbortSignal): void {
  listeners.add(listener);
  signal.addEventListener("abort", () => listeners.delete(listener), { once: true });
}

export function resetCalls(): void {
  collection = null;
  record = null;
}

function announce(): void {
  const call = currentCall();
  for (const listener of [...listeners]) listener(call);
}
