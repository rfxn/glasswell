import { getEnvelope } from "../api/client.ts";
import { unwrap } from "../api/envelope.ts";
import type { Figure } from "../api/envelope.ts";
import { selectWell } from "../bus.ts";
import { highlight } from "../glossary/index.ts";
import { termIndex } from "../glossary/store.ts";
import {
  appendContextDate,
  appendContextFact,
  contextGroup,
  figureElement,
  placeholder,
  warningPanels,
} from "./card.ts";
import { formatVintage } from "./format.ts";

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
    host.append(...warningPanels(envelope.meta.warnings));
    host.dataset["state"] = context.neighbors.length === 0 ? "empty" : "populated";
    highlight(host, termIndex());
  } catch {
    host.replaceChildren(
      placeholder(
        "Physical neighbours are unavailable for this well or requested historical view.",
      ),
    );
    host.dataset["state"] = "unavailable";
  } finally {
    host.setAttribute("aria-busy", "false");
  }
}

function neighborContextBody(context: NeighborContext): DocumentFragment {
  const fragment = document.createDocumentFragment();
  const scope = document.createElement("p");
  scope.className = "gw-context-scope";
  scope.textContent =
    "Physical proximity only — these are not model analogs. Geometry is current-only;" +
    ` eligibility keeps completions strictly before ${formatVintage(context.at_date)}.`;
  fragment.append(
    scope,
    contextGroup(
      "Eligible neighbours",
      null,
      context.neighbors.map(neighborItem),
      "No eligible physical neighbours were found inside the requested radius.",
    ),
  );
  const coverage = document.createElement("p");
  coverage.className = "gw-context-scope gw-neighbor-coverage";
  coverage.append(
    "Showing ",
    figureElement(context.coverage.returned, "returned neighbours", context.coverage.returned.d),
    " of ",
    figureElement(context.coverage.eligible, "eligible neighbours", context.coverage.eligible.d),
    " eligible from ",
    figureElement(
      context.coverage.spatial_candidates,
      "spatial candidates",
      context.coverage.spatial_candidates.d,
    ),
    " spatial candidates.",
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
    neighbor.formation_id ?? formationStatusLabel(neighbor.formation_status),
  );
  appendContextFact(facts, "Mapping", formationStatusLabel(neighbor.formation_status));
  item.appendChild(facts);
  return item;
}

function formationStatusLabel(status: NeighborWell["formation_status"]): string {
  return status.replace(/_/g, " ");
}
