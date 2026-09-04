/**
 * Production by pool, where the regulator files below the well.
 *
 * New Mexico files per completion pool and glasswell rolls nothing up, so the well-level chart
 * is a stated absence and this section is where the record actually is. Montana's absence is a
 * different fact -- no `production_grain` decision is registered for it at all -- and the two
 * must never render as one sentence: a registered decision that nothing rolls up is not a
 * registry gap.
 *
 * The pools are drawn with the monthly chart's own table, rekeyed per pool, so a pool filing
 * and a well month carry the same columns, the same null-semantics vocabulary and the same
 * handle per cell. A second table would be a second contract.
 */
import { getEnvelope } from "../api/client.ts";
import { labelFor, unwrap } from "../api/envelope.ts";
import { toChartSeries } from "../chart/series.ts";
import type { ProductionData } from "../chart/series.ts";
import { labelElement } from "../glossary/gw-term.ts";
import { seriesTable } from "./table.ts";

export interface PoolPayload {
  api10: string;
  granularity: string;
  reporting_level: string;
  pools: {
    well_completion_pool: string;
    entity_key: string;
    streams: string[];
    series: Record<string, unknown>;
  }[];
  _lineage?: Record<string, string>;
  _units?: Record<string, string>;
  _basis?: Record<string, string>;
}

export interface PoolCallbacks {
  onExplain(handle: string): void;
  labelTermFor(pointer: string): string | null;
}

function note(text: string, className = "gw-note"): HTMLElement {
  const element = document.createElement("p");
  element.className = className;
  element.textContent = text;
  return element;
}

function ruleLink(path: string): HTMLAnchorElement {
  const link = document.createElement("a");
  link.className = "gw-identity-rule";
  link.href = path;
  link.setAttribute("data-no-glossary", "");
  link.textContent = path.split("/").pop() ?? path;
  return link;
}

/** One pool's filings in the shape the monthly table already knows how to read. */
function asProduction(payload: PoolPayload, index: number): ProductionData {
  const pool = payload.pools[index];
  const prefix = `pools.${index}.series.`;
  const rekey = (source: Record<string, string> | undefined): Record<string, string> =>
    Object.fromEntries(
      Object.entries(source ?? {})
        .filter(([key]) => key.startsWith(prefix))
        .map(([key, value]) => [`series.${key.slice(prefix.length)}`, value]),
    );
  return {
    api10: payload.api10,
    source_id: null,
    granularity: payload.granularity,
    streams: pool?.streams ?? [],
    series: (pool?.series ?? {}) as ProductionData["series"],
    _lineage: rekey(payload._lineage),
    _units: rekey(payload._units),
    _basis: rekey(payload._basis),
  } as ProductionData;
}

export async function renderPools(
  host: HTMLElement,
  path: string,
  query: Record<string, string>,
  links: Record<string, string>,
  callbacks: PoolCallbacks,
): Promise<void> {
  try {
    const envelope = await getEnvelope<PoolPayload>(path, query);
    const payload = unwrap(envelope);
    const frame = document.createElement("div");
    frame.className = "gw-pools";

    const rule = links["reporting_rule"] ?? links["aggregation_rule"];
    if (rule) {
      const line = note(
        "This well's regulator files production per completion pool and glasswell rolls" +
          " nothing up to the well, by ",
      );
      line.appendChild(ruleLink(rule));
      line.append(". These are the filings themselves, and no sum of them is served.");
      frame.appendChild(line);
    }

    if (payload.pools.length === 0) {
      frame.appendChild(note("No pool filings are served for this well at this vintage."));
      host.replaceChildren(frame);
      return;
    }

    payload.pools.forEach((pool, index) => {
      const section = document.createElement("section");
      section.className = "gw-pool";
      const heading = document.createElement("h4");
      heading.className = "gw-pool-title";
      heading.appendChild(
        labelElement(pool.well_completion_pool, labelFor(envelope, "/pools/well_completion_pool")),
      );
      section.appendChild(heading);
      section.appendChild(
        seriesTable(toChartSeries(asProduction(payload, index)), {
          onExplain: callbacks.onExplain,
          labelTermFor: callbacks.labelTermFor,
        }),
      );
      frame.appendChild(section);
    });
    host.replaceChildren(frame);
  } catch (error) {
    host.replaceChildren(note(`The pool filings could not be read: ${String(error)}`));
  }
}
