/**
 * Basin and geology: the published boundary the well's geometry falls in, the plays that stack
 * there, the ingest scope label kept beside them, and whether the two agree.
 *
 * Every line reads a served field. Which basin a well is in is a cross-source mapping decision
 * and it is a row now, so the section names the rule that decided it and never a jurisdiction.
 */
import { derivationFor, labelFor, unwrap } from "../api/envelope.ts";
import type { Envelope } from "../api/envelope.ts";
import { explainHandle } from "../chrome/handle.ts";
import { labelElement } from "../glossary/gw-term.ts";

export interface BasinContext {
  basin_name: string | null;
  basin_class: string;
  basin_overlap: number;
  play_name: string[];
  play_class: string;
  basin_label_filed: string | null;
  label_class: string;
  label_agrees: boolean | null;
  boundary_vintage: string | null;
  geometry_basis: string;
  rule_id: string | null;
}

export interface WellBasin {
  basin_context: BasinContext | null;
}

const OUTSIDE = "outside_published_boundaries";
const NO_GEOMETRY = "no_geometry";
const IN_BOUNDARY = "in_published_boundary";

/**
 * Read from the served class, so the sentence a reader gets is the one the mart decided. The
 * outside sentence names the set that was asked and its published vintage, because "outside"
 * is a finding about a boundary set and a reader is owed which one.
 */
function absence(context: BasinContext): string | null {
  if (context.basin_class === OUTSIDE) {
    const set = context.boundary_vintage
      ? ` The set asked was ${context.boundary_vintage}.`
      : "";
    return (
      "This well's surface point falls outside every basin the published boundary set draws." +
      set +
      " That is an answer about the boundary set, not a gap in the record."
    );
  }
  if (context.basin_class === NO_GEOMETRY) {
    return (
      "No geometry is held for this well, so no boundary can be asked. The basin is unanswered" +
      " rather than absent."
    );
  }
  return null;
}

/**
 * One line of the section: its label, its value, and the ⌾ that resolves the mart run behind
 * it. Every line takes a handle, because a basin nobody can trace to a run of a mart over a
 * checksummed boundary file is exactly the naked answer R6 refuses -- and the rule link beside
 * it answers a different question, which decision was taken, not which run produced this row.
 */
function row(
  list: HTMLDListElement,
  label: string,
  termId: string | null,
  handle: string | null = null,
): HTMLElement {
  const name = document.createElement("dt");
  name.appendChild(labelElement(label, termId));
  const value = document.createElement("dd");
  if (handle) value.appendChild(explainHandle({ label, handle }));
  list.append(name, value);
  return value;
}

function note(text: string, className = "gw-note gw-basin-note"): HTMLElement {
  const element = document.createElement("p");
  element.className = className;
  element.textContent = text;
  return element;
}

function ruleLink(rule: string): HTMLAnchorElement {
  const link = document.createElement("a");
  link.className = "gw-identity-rule";
  link.href = `/v1/conformance/${rule}`;
  link.setAttribute("data-no-glossary", "");
  link.textContent = rule;
  return link;
}

export function renderBasin(host: HTMLElement, well: Envelope<WellBasin>): void {
  const data = unwrap(well);
  const context = data.basin_context;
  const handleFor = (column: string): string | null =>
    derivationFor(data, `/basin_context/${column}`);
  if (!context) {
    host.replaceChildren(
      note(
        "No basin context has been built for this well yet. That is a state of the mart, not a" +
          " fact about the well.",
      ),
    );
    return;
  }

  const list = document.createElement("dl");
  list.className = "gw-facts gw-basin";

  const basin = row(
    list,
    "Basin",
    labelFor(well, "/basin_context/basin_name"),
    handleFor(context.basin_class === IN_BOUNDARY ? "basin_name" : "basin_class"),
  );
  if (context.basin_class === IN_BOUNDARY && context.basin_name) {
    basin.append(context.basin_name);
  } else {
    basin.append(context.basin_class);
    basin.classList.add("gw-absent");
  }

  if (context.play_name.length > 0) {
    const plays = row(
      list,
      "Plays",
      labelFor(well, "/basin_context/play_name"),
      handleFor("play_name"),
    );
    plays.className = "gw-basin-plays";
    for (const name of context.play_name) {
      const chip = document.createElement("span");
      chip.className = "gw-basin-play";
      chip.textContent = name;
      plays.append(chip, " ");
    }
  } else {
    const plays = row(
      list,
      "Plays",
      labelFor(well, "/basin_context/play_name"),
      handleFor("play_class"),
    );
    plays.append(context.play_class);
    plays.classList.add("gw-absent");
  }

  // The label is kept beside the polygon and marked, never overwritten: a reader who has been
  // reading `permian` for a year needs to see it move, and the disagreement is the finding.
  const filed = row(
    list,
    "Filed label",
    labelFor(well, "/basin_context/basin_label_filed"),
    handleFor(context.basin_label_filed ? "basin_label_filed" : "label_class"),
  );
  filed.className = "gw-basin-label";
  filed.append(context.basin_label_filed ?? context.label_class);
  if (!context.basin_label_filed) filed.classList.add("gw-absent");
  if (context.label_agrees !== null) {
    const mark = document.createElement("span");
    mark.className = context.label_agrees ? "gw-basin-agrees" : "gw-basin-disagrees";
    // Colour is never the only signal: the mark carries the word as well.
    mark.textContent = context.label_agrees
      ? "· agrees with the polygon"
      : "· disagrees with the polygon";
    // The agreement is its own served column and its own claim, so it carries its own ⌾.
    filed.append(" ", mark, explainHandle({ label: "label agreement", handle: handleFor("label_agrees") }));
  }

  if (context.boundary_vintage) {
    const vintage = row(list, "Boundary vintage", null, handleFor("boundary_vintage"));
    vintage.setAttribute("data-no-glossary", "");
    vintage.append(context.boundary_vintage);
  }

  const geometry = row(list, "Answered by", null, handleFor("geometry_basis"));
  geometry.className = "gw-basin-geometry";
  geometry.setAttribute("data-no-glossary", "");
  geometry.append(context.geometry_basis);

  host.replaceChildren(list);

  const unanswered = absence(context);
  if (unanswered) host.appendChild(note(unanswered));
  if (context.basin_overlap > 1) {
    host.appendChild(
      note(
        `${context.basin_overlap} published basins contain this point; the smallest of them is` +
          " served, and the overlap is the publisher's own.",
      ),
    );
  }
  // The scope label is not a finding, and the card says so once wherever one is filed.
  if (context.basin_label_filed) {
    host.appendChild(
      note(
        "The filed label is the slice the ingest took, not a geological finding. It is kept" +
          " here so the two can be read against each other.",
      ),
    );
  }
  if (context.rule_id) {
    const line = note("The rule that decided this: ");
    line.appendChild(ruleLink(context.rule_id));
    host.appendChild(line);
  } else {
    host.appendChild(
      note("This jurisdiction registers no basin context rule, so no basin is decided here."),
    );
  }
}
