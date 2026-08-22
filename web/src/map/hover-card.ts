import { disposalType } from "./disposal.ts";
import { geometryProvenance, provenanceLine } from "./provenance.ts";
import { statusClass } from "./status.ts";
import { statusSwatch } from "./swatch.ts";
import { LIQUIDS_BASIS_COPY, MEMBERSHIP_COPY, MEMBERSHIP_RULE } from "./thematics.ts";

const NUMBER = new Intl.NumberFormat("en-US");

/** A land-grid metrics cell, not a well: the discriminator is the pair no well carries. */
function isMetricsCell(properties: Record<string, unknown>): boolean {
  return typeof properties["land_unit_id"] === "string" && "well_count" in properties;
}

function volume(value: unknown): string {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? NUMBER.format(Math.round(parsed)) : "—";
}

export interface HoverCardHandle {
  element: HTMLElement;
  show(properties: Record<string, unknown>, point: { x: number; y: number }): void;
  hide(): void;
}

/**
 * Hover identifies, click inspects. Everything shown here is already in the tile, so a
 * hover costs one lookup — never a request, and never the full card.
 */
export function createHoverCard(): HoverCardHandle {
  const element = document.createElement("div");
  element.className = "gw-hover";
  element.hidden = true;
  element.setAttribute("aria-hidden", "true");

  const name = document.createElement("p");
  name.className = "gw-hover-name";
  element.appendChild(name);

  const meta = document.createElement("p");
  meta.className = "gw-hover-meta";
  element.appendChild(meta);

  const trace = document.createElement("p");
  trace.className = "gw-hover-meta gw-hover-trace";
  trace.hidden = true;
  element.appendChild(trace);

  const disposal = document.createElement("p");
  disposal.className = "gw-hover-meta gw-hover-disposal";
  disposal.hidden = true;
  element.appendChild(disposal);

  const provenance = document.createElement("p");
  provenance.className = "gw-hover-meta gw-hover-provenance";
  provenance.hidden = true;
  element.appendChild(provenance);

  const figures = document.createElement("p");
  figures.className = "gw-hover-meta gw-hover-figures";
  figures.hidden = true;
  element.appendChild(figures);

  const policy = document.createElement("p");
  policy.className = "gw-hover-meta gw-hover-policy";
  policy.hidden = true;
  element.appendChild(policy);

  const place = (point: { x: number; y: number }): void => {
    element.style.transform = `translate(${point.x + 14}px, ${point.y + 14}px)`;
    element.hidden = false;
  };

  /** M2-3: the cell's figures with their basis and support — never a naked sum. */
  const showCell = (properties: Record<string, unknown>, point: { x: number; y: number }): void => {
    const grain = properties["unit_type"] === "township" ? "Township" : "Section";
    name.textContent = `${grain} ${String(properties["label"] ?? "")}`.trim();
    const wells = volume(properties["well_count"]);
    const producing = volume(properties["prod_well_count"]);
    meta.textContent = `${wells} wells · ${producing} producing`;
    trace.hidden = disposal.hidden = provenance.hidden = true;
    trace.textContent = disposal.textContent = provenance.textContent = "";
    figures.hidden = false;
    figures.textContent =
      `Liquid ${volume(properties["liquid_cum_bbl"])} bbl · ` +
      `gas ${volume(properties["gas_cum_mcf"])} mcf · ` +
      `water ${volume(properties["water_cum_bbl"])} bbl — observed sums`;
    policy.hidden = false;
    policy.textContent =
      `Liquid is ${LIQUIDS_BASIS_COPY}; ${MEMBERSHIP_COPY} (${MEMBERSHIP_RULE}).`;
    place(point);
  };

  return {
    element,
    show(properties, point) {
      if (isMetricsCell(properties)) {
        showCell(properties, point);
        return;
      }
      figures.hidden = policy.hidden = true;
      figures.textContent = policy.textContent = "";
      const api10 = String(properties["api10"] ?? "");
      const wellName = String(properties["well_name"] ?? "").trim();
      const status = statusClass(properties["status_canonical"] as string | undefined);
      name.textContent = wellName || api10;
      meta.replaceChildren(statusSwatch(status.colour, status.glyph, 11));
      // The tile carries no well name today, so repeating the api10 under itself would be
      // the only thing this line said.
      meta.appendChild(document.createTextNode(wellName ? ` ${status.label} · ${api10}` : ` ${status.label}`));
      trace.hidden = properties["geometry_provenance"] !== "survey_trace";
      // Cleared, not just hidden: textContent reads through `hidden`, and so do tests.
      trace.textContent = "";
      if (!trace.hidden) {
        // Deepest *measured depth*, never a length: the trace is the plan view of a 3-D
        // path, so a length over it would measure horizontal travel and understate the hole.
        const stations = Number(properties["station_count"]);
        const deepest = Number(properties["deepest_station_md_ft"]);
        const facts = ["Survey trace"];
        if (Number.isFinite(stations) && stations > 0) facts.push(`${stations} stations`);
        if (Number.isFinite(deepest) && deepest > 0) {
          facts.push(`deepest station ${Math.round(deepest).toLocaleString("en-US")} ft MD`);
        }
        trace.textContent = facts.join(" · ");
      }
      // The verbatim code, never an English decode: which words SWD abbreviates is the
      // regulator's PDF footnote to own, and cr_nd_well_type_disposal_1 asserts none.
      const wellType = disposalType(properties);
      disposal.hidden = wellType === null;
      disposal.textContent = disposal.hidden ? "" : `Disposal / injection · well_type ${wellType} as ND filed it`;
      // M1-3: provenance-of-record at hover, the class verbatim. The trace line above
      // already states its own; a TX feature carries no property and the line stays hidden
      // (the TX half is licence-gated on RF-1 — the legend states it where the reader looks).
      const provenanceClass = geometryProvenance(properties);
      const sentence = provenanceClass === null ? null : provenanceLine(provenanceClass);
      provenance.hidden = sentence === null;
      provenance.textContent = sentence ?? "";
      element.style.transform = `translate(${point.x + 14}px, ${point.y + 14}px)`;
      element.hidden = false;
    },
    hide() {
      element.hidden = true;
    },
  };
}
