/**
 * The peer control: what a held-out subject's peers did, drawn beside nothing.
 *
 * It is not a forecast and the section never uses the word: `relation` says
 * `control_type_curve_not_a_forecast` on the wire and the card renders that verbatim. It is a
 * backward-looking aggregate over an arm this well was held out of, on a producing-month axis,
 * and every sentence that makes it readable -- the quantile convention, the ladder rung the
 * peers were drawn at, the pad-group exclusion, the knowledge cutoff -- is served rather than
 * written here.
 */
import { getEnvelope } from "../api/client.ts";
import { derivationFor, labelFor, unwrap } from "../api/envelope.ts";
import type { Envelope } from "../api/envelope.ts";
import { explainHandle } from "../chrome/handle.ts";
import { labelElement } from "../glossary/gw-term.ts";
import { formatValue } from "./format.ts";

export interface PeerControl {
  api10: string;
  outcome: string;
  relation: string;
  publication_id: string;
  split_set_id: string;
  split_id: string;
  split_sha256: string;
  origin: string | null;
  knowledge_cutoff: string | null;
  eval_vintage: string | null;
  horizon_months: number;
  stream: string;
  normalization: string;
  quantile_convention: string;
  fallback_level: string;
  control_unavailable_reasons: string[];
  peer_set_id: string | null;
  formation_group: string | null;
  area: string | null;
  lateral_length_bucket: string | null;
  series: {
    month_index: number[];
    monthly_p10: (string | null)[];
    monthly_p50: (string | null)[];
    monthly_p90: (string | null)[];
    peer_count: (number | null)[];
  };
}

export interface PeerCallbacks {
  onExplain(handle: string): void;
}

/** The rung the peers were drawn at, in the words the response uses for it. */
function ladder(control: PeerControl): string {
  const rung = [control.formation_group, control.area, control.lateral_length_bucket]
    .filter(Boolean)
    .join(" · ");
  return rung || control.fallback_level;
}

function note(text: string, className = "gw-note"): HTMLElement {
  const element = document.createElement("p");
  element.className = className;
  element.textContent = text;
  return element;
}

function facts(control: PeerControl, envelope: Envelope<PeerControl>): HTMLElement {
  const list = document.createElement("dl");
  list.className = "gw-facts gw-peer-facts";
  const rows: [string, string, string | null][] = [
    ["Relation", control.relation, "/relation"],
    ["Quantile convention", control.quantile_convention, "/quantile_convention"],
    ["Peer ladder", ladder(control), null],
    ["Peer set", control.peer_set_id ?? "none served", null],
    ["Horizon", `${control.horizon_months} months`, null],
    ["Knowledge cutoff", control.knowledge_cutoff ?? "none served", null],
  ];
  for (const [label, value, pointer] of rows) {
    const term = document.createElement("dt");
    term.appendChild(labelElement(label, pointer ? labelFor(envelope, pointer) : null));
    const cell = document.createElement("dd");
    cell.setAttribute("data-no-glossary", "");
    cell.textContent = value;
    list.append(term, cell);
  }
  return list;
}

/** The split this subject was held out in, closed: identity a reader can check, not read. */
function splitIdentity(control: PeerControl): HTMLElement {
  const details = document.createElement("details");
  details.className = "gw-peer-split";
  const summary = document.createElement("summary");
  summary.textContent = "Which split held this well out";
  details.appendChild(summary);
  const list = document.createElement("dl");
  list.className = "gw-facts";
  for (const [label, value] of [
    ["Split set", control.split_set_id],
    ["Split", control.split_id],
    ["Split sha256", control.split_sha256],
    ["Publication", control.publication_id],
    ["Evaluation vintage", control.eval_vintage ?? "none served"],
  ] as [string, string][]) {
    const term = document.createElement("dt");
    term.textContent = label;
    const cell = document.createElement("dd");
    cell.className = "gw-peer-identity";
    cell.setAttribute("data-no-glossary", "");
    cell.textContent = value;
    list.append(term, cell);
  }
  details.appendChild(list);
  return details;
}

/**
 * The control as a table, which is its data-table alternative and its only rendering here: a
 * second plot on the card would need a second chart chunk on the card's route, and the three
 * quantiles with a peer count per month is a table before it is a picture.
 */
function controlTable(
  control: PeerControl,
  envelope: Envelope<PeerControl>,
  callbacks: PeerCallbacks,
): HTMLElement {
  const frame = document.createElement("div");
  frame.className = "gw-series-table gw-peer-table";
  const table = document.createElement("table");
  const caption = document.createElement("caption");
  caption.textContent =
    `The peer control on a producing-month axis: ${control.series.month_index.length} months,` +
    ` P10, P50 and P90 with the peers behind each month. Knowledge cutoff` +
    ` ${control.knowledge_cutoff ?? "not served"}.`;
  table.appendChild(caption);

  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  const columns: [string, string | null][] = [
    ["Producing month", "/series/month_index"],
    ["P10", null],
    ["P50", null],
    ["P90", null],
    ["Peers", "/series/peer_count"],
  ];
  for (const [label, pointer] of columns) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.appendChild(labelElement(label, pointer ? labelFor(envelope, pointer) : null));
    headRow.appendChild(cell);
  }
  head.appendChild(headRow);
  table.appendChild(head);

  const body = document.createElement("tbody");
  control.series.month_index.forEach((month, index) => {
    const row = document.createElement("tr");
    const when = document.createElement("th");
    when.scope = "row";
    when.setAttribute("data-no-glossary", "");
    when.textContent = String(month);
    row.appendChild(when);
    for (const values of [
      control.series.monthly_p10,
      control.series.monthly_p50,
      control.series.monthly_p90,
    ]) {
      const cell = document.createElement("td");
      cell.className = "gw-table-value";
      cell.setAttribute("data-no-glossary", "");
      const value = values[index];
      cell.textContent = value === null || value === undefined ? "" : formatValue(value);
      row.appendChild(cell);
    }
    const peers = document.createElement("td");
    peers.className = "gw-table-value";
    peers.setAttribute("data-no-glossary", "");
    peers.textContent = String(control.series.peer_count[index] ?? "");
    row.appendChild(peers);
    body.appendChild(row);
  });
  table.appendChild(body);
  frame.appendChild(table);
  void callbacks;
  return frame;
}

/** Where the control could not be drawn, its reasons and its slots, both served. */
function unavailable(control: PeerControl): HTMLElement {
  const frame = document.createElement("div");
  frame.className = "gw-peer-unavailable";
  frame.appendChild(
    note(
      "No control is served for this well at this rung. The reasons are the publication's" +
        " own, and the slots below stay in place rather than being filled with a number" +
        " nobody produced.",
    ),
  );
  const list = document.createElement("ul");
  list.className = "gw-peer-reasons";
  for (const reason of control.control_unavailable_reasons) {
    const item = document.createElement("li");
    item.setAttribute("data-no-glossary", "");
    item.textContent = reason;
    list.appendChild(item);
  }
  if (control.control_unavailable_reasons.length > 0) frame.appendChild(list);
  return frame;
}

export async function renderPeerControl(
  host: HTMLElement,
  path: string,
  query: Record<string, string>,
  callbacks: PeerCallbacks,
): Promise<void> {
  try {
    const envelope = await getEnvelope<PeerControl>(path, query);
    const control = unwrap(envelope);
    const frame = document.createElement("section");
    frame.className = "gw-peer";

    const heading = document.createElement("h4");
    heading.className = "gw-peer-title";
    heading.textContent = "Peer control";
    frame.appendChild(heading);
    // Verbatim, and never the word forecast: the wire says what this is, and a client that
    // paraphrased it would be the one place the claim could drift.
    frame.appendChild(note(control.relation, "gw-note gw-peer-relation"));
    frame.appendChild(facts(control, envelope));
    frame.appendChild(
      note(
        "The subject is held out of the fit, and every well on its pad with it: a control" +
          " fitted on a neighbour of this well and then compared against it would be reading" +
          " its own training data one pad over.",
      ),
    );
    if (control.outcome === "control_unavailable") {
      frame.appendChild(unavailable(control));
    } else {
      frame.appendChild(controlTable(control, envelope, callbacks));
    }
    frame.appendChild(splitIdentity(control));

    // The section's own ⌾, taken from the first handle the response advertises: the drawer
    // opens at the default depth and the chain says itself where it was truncated.
    const first = derivationFor(control, "/series/monthly_p50");
    if (first) {
      const line = note("");
      line.appendChild(
        explainHandle({
          label: "the peer control",
          handle: first,
          activate: (id) => callbacks.onExplain(id),
        }),
      );
      line.append(" Every quantile above resolves to the publication that produced it.");
      frame.appendChild(line);
    }
    host.replaceChildren(frame);
  } catch (error) {
    host.replaceChildren(note(`The peer control could not be read: ${String(error)}`));
  }
}
