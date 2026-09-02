import { ApiError, getEnvelope } from "../api/client.ts";
import { unwrap } from "../api/envelope.ts";
import type { Figure } from "../api/envelope.ts";
import { selectWell } from "../bus.ts";
import { disclosure, emptyState, scopeLine, unbreakable, warningNotes, warningTitle } from "../chrome/notes.ts";
import { highlight } from "../glossary/index.ts";
import { termIndex } from "../glossary/store.ts";
import {
  appendContextDate,
  appendContextFact,
  contextGroup,
  figureElement,
} from "./card.ts";
import { absentValue, formatVintage } from "./format.ts";

interface NeighborWell {
  neighbor_api10: string;
  distance_ft: Figure;
  completion_date: string;
  formation_id: string | null;
  formation_status: "mapped" | "pool_unavailable" | "alias_unavailable" | "below_confidence" | "conflict";
}

interface NeighborContext {
  api10: string;
  at_date: string;
  geometry_scope: "current_only";
  relation: "physical_neighbours_not_model_analogs";
  coverage: Record<"spatial_candidates" | "eligible" | "returned", Figure>;
  neighbors: NeighborWell[];
}

export async function loadNeighborContext(
  host: HTMLElement,
  path: string,
  expectedApi10: string,
  query: Record<string, string>,
): Promise<void> {
  try {
    const envelope = await getEnvelope<NeighborContext>(path, query);
    const context = unwrap(envelope);
    if (
      context.api10 !== expectedApi10 ||
      context.geometry_scope !== "current_only" ||
      context.relation !== "physical_neighbours_not_model_analogs" ||
      !Array.isArray(context.neighbors) ||
      !context.coverage
    ) {
      throw new TypeError("Neighbour context did not match the required well and contract");
    }
    host.replaceChildren(neighborContextBody(context));
    host.append(...warningNotes(envelope.meta.warnings));
    host.dataset["state"] = context.neighbors.length === 0 ? "empty" : "populated";
    highlight(host, termIndex());
  } catch (error) {
    host.replaceChildren(...unavailable(error));
    host.dataset["state"] = "unavailable";
  } finally {
    host.setAttribute("aria-busy", "false");
  }
}

/**
 * The endpoint refuses a subject with no completion anchor by naming the parameter that would
 * unblock it. That refusal was being caught and replaced with "unavailable for this well or
 * requested historical view", which is vaguer than what the server said and drops the way out.
 */
function unavailable(error: unknown): HTMLElement[] {
  if (!(error instanceof ApiError)) {
    return [emptyState("Unavailable: the response could not be read.")];
  }
  // The code over the title: `type` names what was refused, where `title` is the generic
  // family ("Not authenticated") every problem of that status shares.
  const named = error.problem.errors?.find((entry) => entry.code)?.code ?? error.code;
  const detail = error.problem.errors?.[0]?.detail ?? error.problem.detail;
  const summary = warningTitle(named);
  return detail ? [disclosure(summary, detail)] : [emptyState(summary)];
}

function neighborContextBody(context: NeighborContext): DocumentFragment {
  const fragment = document.createDocumentFragment();
  fragment.append(
    scopeLine([
      "Proximity, not analogs",
      "current geometry",
      unbreakable(`completed before ${formatVintage(context.at_date)}`),
    ]),
    contextGroup(
      "Eligible neighbours",
      null,
      context.neighbors.map(neighborItem),
      "None inside the radius",
    ),
  );
  // Three figures and two words, rather than a sentence with three figures inside it: the
  // funnel is what the reader is being shown, and it reads as one now.
  const coverage = document.createElement("p");
  coverage.className = "gw-scope gw-neighbor-coverage";
  coverage.append(
    figureElement(context.coverage.returned, "returned neighbours", context.coverage.returned.d),
    " shown · ",
    figureElement(context.coverage.eligible, "eligible neighbours", context.coverage.eligible.d),
    " eligible · ",
    figureElement(
      context.coverage.spatial_candidates,
      "spatial candidates",
      context.coverage.spatial_candidates.d,
    ),
    " in radius",
  );
  fragment.appendChild(coverage);
  return fragment;
}

function neighborItem(neighbor: NeighborWell): HTMLElement {
  const item = document.createElement("li");
  const heading = document.createElement("a");
  heading.className = "gw-neighbor-link";
  heading.href = `/?well=${neighbor.neighbor_api10}`;
  heading.textContent = neighbor.neighbor_api10;
  heading.setAttribute("data-no-glossary", "");
  heading.addEventListener("click", (event) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    selectWell(neighbor.neighbor_api10, "card");
  });
  item.appendChild(heading);
  const facts = document.createElement("dl");
  facts.className = "gw-context-facts";
  appendContextFact(
    facts,
    "Distance",
    figureElement(neighbor.distance_ft, "physical distance", neighbor.distance_ft.d),
  );
  appendContextDate(facts, "Completed", neighbor.completion_date);
  appendContextFact(
    facts,
    "Formation",
    neighbor.formation_id ?? absentValue(FORMATION_ABSENCE[neighbor.formation_status] ?? null),
  );
  appendContextFact(facts, "Mapping", MAPPING_STATE[neighbor.formation_status] ?? neighbor.formation_status);
  item.appendChild(facts);
  return item;
}

/**
 * The neighbour endpoint's own null semantics, spelled out. The rows used to render the raw
 * enum token, so "pool unavailable" stood in the Formation cell looking exactly like a
 * formation name. This vocabulary is not asserted to mean the same as the completions
 * endpoint's; only the form the two are rendered in is shared.
 */
const FORMATION_ABSENCE: Record<string, string> = {
  pool_unavailable: "no pool on the neighbour's record",
  alias_unavailable: "no registered alias",
  below_confidence: "alias match below the confidence floor",
  conflict: "the registered aliases disagree",
};

/** The mapping state itself, which is a value and not an absence, so it carries no mark. */
const MAPPING_STATE: Record<string, string> = {
  mapped: "mapped",
  pool_unavailable: "no pool reported",
  alias_unavailable: "no registered alias",
  below_confidence: "below the confidence floor",
  conflict: "aliases disagree",
};
