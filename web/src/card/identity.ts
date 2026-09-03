/**
 * Whose well it is: the jurisdiction, the regulator, the code the regulator filed, and the
 * history of that code where the jurisdiction's clock has one.
 *
 * Every per-jurisdiction sentence here reads a served field. The registry answers who the
 * regulator is and which rules decided what; the response says whether there is a history to
 * ask for. Nothing on this surface knows a state by name.
 */
import { getEnvelope } from "../api/client.ts";
import { labelFor, unwrap } from "../api/envelope.ts";
import type { Envelope } from "../api/envelope.ts";
import { labelElement } from "../glossary/gw-term.ts";

export interface WellIdentity {
  api10: string;
  state_code: string | null;
  status_reported: string | null;
  status_canonical: string | null;
  status_vocabulary_rule: string | null;
  well_type_reported: string | null;
  producing: string | null;
  geometry: { geom_type: string; geom_key: string; source_datum: string }[];
  geometry_provenance: string[] | null;
  geometry_provenance_rule: string | null;
  jurisdiction_name: string | null;
  regulator_name: string | null;
  regulator_url: string | null;
}

export interface StatusHistoryRow {
  effective_from: string;
  status_reported: string | null;
  status_canonical: string | null;
  status_rule_id: string | null;
}

export interface StatusHistory {
  api10: string;
  basis: {
    clock: string;
    served: boolean;
    rule_id: string | null;
    status_vocabulary_rule: string | null;
    class_column_label: string;
    class_column_is_historical: boolean;
    detail: string;
  };
  history: StatusHistoryRow[];
  cap: { limit: number; returned: number; total: number; withheld: number };
}

const RULE_PATH = "/v1/conformance/";

function ruleLink(rule: string, text: string): HTMLAnchorElement {
  const link = document.createElement("a");
  link.className = "gw-identity-rule";
  link.href = rule.startsWith("/") ? rule : `${RULE_PATH}${rule}`;
  link.setAttribute("data-no-glossary", "");
  link.textContent = text;
  return link;
}

function row(list: HTMLDListElement, label: string, termId: string | null): HTMLElement {
  const name = document.createElement("dt");
  name.appendChild(labelElement(label, termId));
  const value = document.createElement("dd");
  list.append(name, value);
  return value;
}

function note(text: string): HTMLElement {
  const element = document.createElement("p");
  element.className = "gw-note gw-identity-note";
  element.textContent = text;
  return element;
}

/**
 * The status, in the order a reader needs it: what the regulator filed, then what glasswell
 * makes of it. The chip in the card's head is built only when a class resolves, which on the
 * deployed instance leaves 68,186 Texas wells showing no status at all -- not even the code
 * the regulator wrote down. Here the code and the regulator always render (DR-A7).
 */
function statusBlock(list: HTMLDListElement, well: Envelope<WellIdentity>): void {
  const detail = unwrap(well);
  const filed = row(list, "Filed status", labelFor(well, "/status_reported"));
  filed.setAttribute("data-no-glossary", "");
  filed.className = "gw-identity-filed";
  filed.textContent = detail.status_reported ?? "none filed";
  if (detail.regulator_name) {
    const by = document.createElement("span");
    by.className = "gw-fact-qualifier";
    by.textContent = ` · as ${detail.regulator_name} filed it`;
    filed.appendChild(by);
  }

  const klass = row(list, "Class", labelFor(well, "/status_canonical"));
  klass.className = "gw-identity-class";
  if (detail.status_canonical) {
    klass.textContent = detail.status_canonical;
  } else {
    // Two different absences, and the card says which. A code nobody has mapped is unmapped;
    // no code at all is nothing to map.
    klass.textContent = detail.status_reported ? "unmapped" : "unresolved";
    klass.classList.add("gw-absent");
  }
  if (detail.status_vocabulary_rule) {
    klass.append(" ", ruleLink(detail.status_vocabulary_rule, detail.status_vocabulary_rule));
  }
}

function jurisdictionBlock(list: HTMLDListElement, well: Envelope<WellIdentity>): void {
  const detail = unwrap(well);
  if (!detail.jurisdiction_name && !detail.regulator_name) return;
  const value = row(list, "Filed with", labelFor(well, "/jurisdiction_name"));
  value.className = "gw-identity-jurisdiction";
  if (detail.jurisdiction_name) value.append(`${detail.jurisdiction_name} · `);
  if (detail.regulator_name && detail.regulator_url) {
    const link = document.createElement("a");
    link.className = "gw-identity-regulator";
    link.href = detail.regulator_url;
    link.rel = "noreferrer";
    link.textContent = detail.regulator_name;
    value.appendChild(link);
  } else if (detail.regulator_name) {
    value.append(detail.regulator_name);
  }
}

function wellTypeBlock(list: HTMLDListElement, well: Envelope<WellIdentity>): void {
  const detail = unwrap(well);
  if (!detail.well_type_reported) return;
  const value = row(list, "Well type", labelFor(well, "/well_type_reported"));
  value.className = "gw-identity-well-type";
  value.setAttribute("data-no-glossary", "");
  // The hover was a bare code, so a Montana disposal well read as North Dakota filed it. The
  // regulator's own name comes off the registry, not out of a lookup written here.
  value.textContent = detail.regulator_name
    ? `${detail.well_type_reported} · as ${detail.regulator_name} filed it`
    : detail.well_type_reported;
}

function geometryBlock(
  host: HTMLElement,
  list: HTMLDListElement,
  well: Envelope<WellIdentity>,
): void {
  const detail = unwrap(well);
  if (detail.producing) {
    const value = row(list, "Producing", labelFor(well, "/producing"));
    value.setAttribute("data-no-glossary", "");
    value.textContent = detail.producing;
  }
  if (detail.state_code) {
    const value = row(list, "API state prefix", labelFor(well, "/state_code"));
    value.className = "gw-fact-mono";
    value.setAttribute("data-no-glossary", "");
    value.textContent = detail.state_code;
  }
  if (detail.geometry.length > 0) {
    const value = row(list, "Geometry held", labelFor(well, "/geometry"));
    value.className = "gw-identity-geometry";
    value.setAttribute("data-no-glossary", "");
    value.textContent = detail.geometry
      .map((item) => `${item.geom_type} (${item.source_datum})`)
      .join(", ");
  }
  if (detail.geometry_provenance_rule) {
    const value = row(list, "Geometry rule", labelFor(well, "/geometry_provenance_rule"));
    value.appendChild(
      ruleLink(detail.geometry_provenance_rule, detail.geometry_provenance_rule),
    );
  } else {
    // A registry gap, and a fact about the registry rather than about the well. Inheriting
    // another jurisdiction's rule here is exactly the mislabel this section exists to end.
    host.appendChild(
      note(
        "This jurisdiction registers no geometry provenance rule, so what its geometry means" +
          " is not yet a decision anyone can read. It is a gap in the registry, not a fact" +
          " about this well.",
      ),
    );
  }
}

function historyTable(envelope: Envelope<StatusHistory>, history: StatusHistory): HTMLElement {
  const frame = document.createElement("div");
  frame.className = "gw-status-history";
  const table = document.createElement("table");
  const caption = document.createElement("caption");
  caption.textContent = "Status history, newest first";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  // The router serves a term pointer for each of these columns; reading them is what makes the
  // header hoverable, and not reading them left four served labels with no consumer (gate M3).
  const columns: [string, string][] = [
    ["Effective from", "/history/effective_from"],
    ["Filed code", "/history/status_reported"],
    [history.basis.class_column_label, "/history/status_canonical"],
  ];
  for (const [label, pointer] of columns) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.appendChild(labelElement(label, labelFor(envelope, pointer)));
    headRow.appendChild(cell);
  }
  head.appendChild(headRow);
  const body = document.createElement("tbody");
  for (const entry of history.history) {
    const line = document.createElement("tr");
    const when = document.createElement("td");
    when.setAttribute("data-no-glossary", "");
    when.textContent = entry.effective_from;
    const filed = document.createElement("td");
    filed.setAttribute("data-no-glossary", "");
    filed.textContent = entry.status_reported ?? "none filed";
    const klass = document.createElement("td");
    klass.textContent = entry.status_canonical ?? "unmapped";
    if (!entry.status_canonical) klass.classList.add("gw-absent");
    if (entry.status_rule_id) {
      klass.append(" ", ruleLink(entry.status_rule_id, entry.status_rule_id));
    }
    line.append(when, filed, klass);
    body.appendChild(line);
  }
  table.append(caption, head, body);
  frame.appendChild(table);
  // Said once, under the table, because the column header cannot carry it: the class is a
  // read-time join against today's registry, so a superseded vocabulary rule restates every
  // row at once and the regulator never moved.
  frame.appendChild(
    note(
      "The class column is today's mapping applied to a historical code, not the class that" +
        " was in force when the code was filed. Each row names the rule that produced it.",
    ),
  );
  if (history.cap.withheld > 0) {
    frame.appendChild(
      note(
        `Showing ${history.cap.returned} of ${history.cap.total} filed headers;` +
          ` ${history.cap.withheld} older ones are not on this page.`,
      ),
    );
  }
  return frame;
}

/**
 * Renders the Identity and status section. The history is fetched only where the response
 * offered a link to it, so the card never asks a question the jurisdiction has no answer for.
 */
export async function renderIdentity(
  host: HTMLElement,
  well: Envelope<WellIdentity>,
  bands: HTMLElement,
  query: Record<string, string>,
): Promise<void> {
  const list = document.createElement("dl");
  list.className = "gw-facts gw-identity";
  jurisdictionBlock(list, well);
  statusBlock(list, well);
  wellTypeBlock(list, well);
  host.append(list, bands);
  geometryBlock(host, list, well);

  // The regulator link is a portal root: no per-well URL template is registered for any
  // jurisdiction, so a link labelled as the record for this well would be a lie the size of
  // one click. Said on the card rather than assumed by the reader.
  if (unwrap(well).regulator_url) {
    host.appendChild(
      note("The regulator link opens that regulator's portal, not this well's own record."),
    );
  }

  const path = well.links?.["history"];
  if (!path) {
    // Not "this well never changed": no history was captured here, and the card says which
    // jurisdiction that is, by name, off the served field the row above already prints.
    const rule = well.links?.["status_rule"];
    const subject = unwrap(well).jurisdiction_name ?? "This jurisdiction";
    const line = note(
      `${subject} files a snapshot, so this record has no status history: the date beside a` +
        " filed code here is the vintage of the extract glasswell pulled, not a date the" +
        " regulator stamped.",
    );
    if (rule) line.append(" ", ruleLink(rule, "The rule that decides that"));
    host.appendChild(line);
    return;
  }

  try {
    const envelope = await getEnvelope<StatusHistory>(path, query);
    const history = unwrap(envelope);
    if (history.history.length === 0) {
      host.appendChild(note(history.basis.detail));
      return;
    }
    host.appendChild(historyTable(envelope, history));
  } catch (error) {
    host.appendChild(note(`The status history could not be read: ${String(error)}`));
  }
}
