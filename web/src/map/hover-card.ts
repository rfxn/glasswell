import { explainHandle, setExplainHandle } from "../chrome/handle.ts";
import { disposalCodebook, injectionCandidate } from "./disposal.ts";
import { BY_PREFIX } from "./jurisdictions.generated.ts";
import { geometryProvenance, provenanceLine } from "./provenance.ts";
import { statusClass } from "./status.ts";
import { statusSwatch } from "./swatch.ts";
import { LIQUIDS_BASIS_COPY, MEMBERSHIP_COPY, MEMBERSHIP_RULE } from "./thematics.ts";

const NUMBER = new Intl.NumberFormat("en-US");

export const CURSOR_OFFSET = 14;

export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

interface Point {
  x: number;
  y: number;
}

interface Size {
  width: number;
  height: number;
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(Math.max(value, low), Math.max(low, high));
}

function overlaps(x: number, y: number, size: Size, avoid: Rect | null): boolean {
  return (
    avoid !== null &&
    x < avoid.right &&
    x + size.width > avoid.left &&
    y < avoid.bottom &&
    y + size.height > avoid.top
  );
}

/**
 * Edge-aware cursor anchoring (visual-m13 / visual-m23 V-1): below-right of the cursor
 * until that clips, then flipped left of it and/or above it; among the corners that fit
 * the canvas, one that clears `avoid` — the on-canvas key — wins. Only a card too big
 * for any corner is clamped to the canvas instead.
 */
export function placeCard(
  point: Point,
  size: Size,
  viewport: Size,
  avoid: Rect | null = null,
): Point {
  const fitsX = (x: number): boolean => x >= 0 && x + size.width <= viewport.width;
  const fitsY = (y: number): boolean => y >= 0 && y + size.height <= viewport.height;
  const right = point.x + CURSOR_OFFSET;
  const left = point.x - CURSOR_OFFSET - size.width;
  const below = point.y + CURSOR_OFFSET;
  const above = point.y - CURSOR_OFFSET - size.height;
  const xs = fitsX(right) ? [right, left] : [left, right];
  const ys = fitsY(below) ? [below, above] : [above, below];
  const corners = [
    { x: xs[0]!, y: ys[0]! },
    { x: xs[1]!, y: ys[0]! },
    { x: xs[0]!, y: ys[1]! },
    { x: xs[1]!, y: ys[1]! },
  ];
  const fitting = corners.filter((corner) => fitsX(corner.x) && fitsY(corner.y));
  for (const corner of fitting) {
    if (!overlaps(corner.x, corner.y, size, avoid)) return corner;
  }
  const base = fitting[0] ?? corners[0]!;
  return {
    x: clamp(base.x, 0, viewport.width - size.width),
    y: clamp(base.y, 0, viewport.height - size.height),
  };
}

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

export interface HoverCardOptions {
  /** The on-canvas rect placement must dodge when it can — the thematic key. */
  avoid?: () => Rect | null;
}

/**
 * Hover identifies, click inspects. Everything shown here is already in the tile, so a
 * hover costs one lookup — never a request, and never the full card.
 */
export function createHoverCard(options: HoverCardOptions = {}): HoverCardHandle {
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

  // gate-m23 cycle-1 item 8: the cell figures resolve on the card itself, so a cropped
  // screenshot of it still carries the affordance the key holds.
  const handle = explainHandle({ className: "gw-hover-handle", label: "these cell figures" });
  // Focusable content inside `aria-hidden` is a control a keyboard reader can reach and hear
  // nothing about. This card only ever appears under a pointer, and the same derivation reaches
  // the keyboard through the Layers panel, so the ⌾ keeps its click and gives up Tab.
  handle.tabIndex = -1;
  element.appendChild(handle);

  const place = (point: { x: number; y: number }): void => {
    // Shown before measuring: a hidden element has no offset box to measure.
    element.hidden = false;
    const host = element.parentElement;
    const size = { width: element.offsetWidth, height: element.offsetHeight };
    // happy-dom and a pre-mount card measure zero; the plain cursor anchor stands in.
    const spot =
      host && host.clientWidth > 0 && size.width > 0
        ? placeCard(
            point,
            size,
            { width: host.clientWidth, height: host.clientHeight },
            options.avoid?.() ?? null,
          )
        : { x: point.x + CURSOR_OFFSET, y: point.y + CURSOR_OFFSET };
    element.style.transform = `translate(${spot.x}px, ${spot.y}px)`;
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
      `water ${volume(properties["water_cum_bbl"])} bbl · observed sums`;
    policy.hidden = false;
    policy.textContent =
      `Liquid is ${LIQUIDS_BASIS_COPY}; ${MEMBERSHIP_COPY} (${MEMBERSHIP_RULE}).`;
    const derivation = properties["derivation_id"];
    const handleId = typeof derivation === "string" && derivation !== "" ? derivation : null;
    setExplainHandle(handle, handleId);
    // The live ⌾ needs the pointer, so only the cell card takes it (see map.css).
    element.classList.add("gw-hover-cell");
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
      figures.textContent = "";
      policy.textContent = "";
      setExplainHandle(handle, null);
      element.classList.remove("gw-hover-cell");
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
      //
      // Two sentences, because there are two facts and only one of them is registered
      // everywhere. The code and the regulator that filed it are always knowable, and this
      // line used to say "as ND filed it" over every jurisdiction on a code list that is North
      // Dakota's. Whether another regulator means by the code what the NDIC means is a
      // decision, and only North Dakota has published one -- so the class and its rule are
      // named where a codebook is registered, and their absence is stated where none is,
      // rather than the whole line disappearing, which reads as though the well were not an
      // injector at all.
      const candidate = injectionCandidate(properties);
      const codebook = disposalCodebook(api10);
      const filer = BY_PREFIX[api10.slice(0, 2)]?.code ?? null;
      disposal.hidden = candidate === null || filer === null;
      const filed = `well_type ${candidate} as ${filer} filed it`;
      disposal.textContent = disposal.hidden
        ? ""
        : codebook !== null && codebook.codes.includes(candidate!)
          ? `Disposal / injection · ${filed} · ${codebook.rule}`
          : `${filed} · no injection codebook is registered for ${filer}`;
      // M1-3: provenance-of-record at hover, the class verbatim. The trace line above
      // already states its own; a TX feature carries no property and the line stays hidden
      // (the TX half is licence-gated on RF-1 — the legend states it where the reader looks).
      const provenanceClass = geometryProvenance(properties);
      const sentence = provenanceClass === null ? null : provenanceLine(provenanceClass, api10);
      provenance.hidden = sentence === null;
      provenance.textContent = sentence ?? "";
      place(point);
    },
    hide() {
      element.hidden = true;
    },
  };
}
