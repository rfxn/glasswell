import { ApiError, getEnvelope } from "../api/client.ts";
import { focusPanel } from "../chrome/overlays.ts";
import { unwrap } from "../api/envelope.ts";
import { highlight } from "../glossary/index.ts";
import { termIndex } from "../glossary/store.ts";

export interface ChainNode {
  id: string;
  type: "derivation" | "manifest" | "rule" | "model" | "external";
  explanation: string;
  sha256?: string;
  bytes?: number;
  acquisition_url?: string;
  acquisition_method?: string;
  fetched_at?: string;
  fetch_vintage?: string;
  source_id?: string;
  source_key?: string;
  operation?: string;
  code_version?: string;
  determinism_class?: string;
  conformance_rules?: { rule_id: string }[];
}

export interface Chain {
  handle: string;
  root: string;
  depth: number;
  truncated: boolean;
  as_of_vintage: string | null;
  nodes: ChainNode[];
  terminals: string[];
  recipe: string | null;
  warnings: string[];
}

export interface DrawerCallbacks {
  onClose(): void;
}

/** S9: one /v1/explain call renders the whole chain, checksums included, at depth full. */
export async function renderLineageDrawer(
  container: HTMLElement,
  handle: string,
  callbacks: DrawerCallbacks,
): Promise<void> {
  container.hidden = false;
  container.replaceChildren(header(handle, callbacks), panelBody(loading()));

  try {
    const envelope = await getEnvelope<{ chains: Chain[] }>("/v1/explain", {
      h: handle,
      depth: "full",
    });
    const chain = unwrap(envelope).chains[0];
    if (!chain) {
      container.replaceChildren(
        header(handle, callbacks),
        panelBody(message("No chain came back.")),
      );
      return;
    }
    const body = panelBody(summary(chain), nodeList(chain));
    container.replaceChildren(header(handle, callbacks), body);
    highlight(body, termIndex());
    focusPanel(container);
  } catch (error) {
    container.replaceChildren(header(handle, callbacks), panelBody(unresolved(error)));
  }
}

function panelBody(...children: HTMLElement[]): HTMLElement {
  const element = document.createElement("div");
  element.className = "gw-panel-body gw-drawer-body";
  element.append(...children);
  return element;
}

function header(handle: string, callbacks: DrawerCallbacks): HTMLElement {
  const element = document.createElement("header");
  element.className = "gw-panel-head gw-drawer-header";
  const heading = document.createElement("h2");
  heading.tabIndex = -1;
  heading.textContent = "Lineage";
  const code = document.createElement("code");
  code.className = "gw-handle-text";
  code.textContent = handle;
  const close = document.createElement("button");
  close.type = "button";
  close.className = "gw-close";
  close.setAttribute("aria-label", "Close the lineage drawer");
  close.textContent = "×";
  close.addEventListener("click", callbacks.onClose);
  element.append(heading, code, close);
  return element;
}

function summary(chain: Chain): HTMLElement {
  const element = document.createElement("p");
  element.className = "gw-drawer-summary";
  element.setAttribute("data-no-glossary", "");
  const parts = [
    `depth ${chain.depth}`,
    `${chain.nodes.length} nodes`,
    `${chain.terminals.length} terminal manifest${chain.terminals.length === 1 ? "" : "s"}`,
  ];
  if (chain.as_of_vintage) parts.push(`vintage ${chain.as_of_vintage}`);
  if (chain.truncated) parts.push("truncated");
  element.textContent = parts.join(" · ");
  return element;
}

function nodeList(chain: Chain): HTMLElement {
  const list = document.createElement("ol");
  list.className = "gw-chain";
  for (const node of chain.nodes) {
    const item = document.createElement("li");
    item.className = `gw-chain-node gw-chain-${node.type}`;

    const kind = document.createElement("span");
    kind.className = "gw-chip gw-chip-kind";
    kind.textContent = node.type === "manifest" ? "MANIFEST" : (node.operation ?? node.type);
    item.appendChild(kind);

    const identifier = document.createElement("code");
    identifier.className = "gw-node-id";
    identifier.textContent = node.id;
    item.appendChild(identifier);

    const explanation = document.createElement("p");
    explanation.className = "gw-node-explanation";
    explanation.textContent = node.explanation;
    item.appendChild(explanation);

    if (node.type === "manifest") item.appendChild(manifestFacts(node));
    else if (node.conformance_rules?.length) item.appendChild(ruleChips(node.conformance_rules));

    list.appendChild(item);
  }
  return list;
}

function manifestFacts(node: ChainNode): HTMLElement {
  const facts = document.createElement("dl");
  facts.className = "gw-manifest";

  if (node.acquisition_url) {
    facts.appendChild(label("source"));
    const value = document.createElement("dd");
    const link = document.createElement("a");
    link.href = node.acquisition_url;
    // Same-tab navigation to a 3 MB XLSX destroys the app state the receipt belongs to.
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = node.acquisition_url;
    value.appendChild(link);
    facts.appendChild(value);
  }
  if (node.fetched_at) {
    facts.appendChild(label("fetched"));
    const value = document.createElement("dd");
    value.setAttribute("data-no-glossary", "");
    value.textContent = `${node.fetched_at}${
      node.fetch_vintage ? ` · vintage ${node.fetch_vintage}` : ""
    }`;
    facts.appendChild(value);
  }
  if (node.sha256) {
    facts.appendChild(label("sha256"));
    const value = document.createElement("dd");
    const digest = document.createElement("code");
    digest.className = "gw-sha256";
    // Selectable, in full: the point is that a stranger can verify the file themselves.
    digest.textContent = node.sha256;
    value.appendChild(digest);
    if (node.bytes !== undefined) {
      const bytes = document.createElement("span");
      bytes.className = "gw-bytes";
      bytes.textContent = ` · ${node.bytes.toLocaleString()} bytes`;
      value.appendChild(bytes);
    }
    facts.appendChild(value);
  }
  return facts;
}

function ruleChips(rules: { rule_id: string }[]): HTMLElement {
  const wrapper = document.createElement("p");
  wrapper.className = "gw-rules";
  for (const rule of rules) {
    const chip = document.createElement("span");
    chip.className = "gw-chip gw-chip-rule";
    chip.setAttribute("data-no-glossary", "");
    chip.textContent = rule.rule_id;
    wrapper.appendChild(chip);
  }
  return wrapper;
}

function label(text: string): HTMLElement {
  const element = document.createElement("dt");
  element.textContent = text;
  return element;
}

function loading(): HTMLElement {
  return message("Resolving the chain…");
}

function message(text: string): HTMLElement {
  const element = document.createElement("p");
  element.className = "gw-placeholder";
  element.textContent = text;
  return element;
}

/** A broken chain renders as a broken chain: last resolved node and stop reason, not a toast. */
function unresolved(error: unknown): HTMLElement {
  const element = document.createElement("div");
  element.className = "gw-error";
  if (error instanceof ApiError) {
    const heading = document.createElement("h3");
    heading.textContent = `${error.problem.title} (${error.code})`;
    element.appendChild(heading);
    const detail = document.createElement("p");
    detail.textContent = error.problem.detail ?? "";
    element.appendChild(detail);
    if (error.problem.last_resolved || error.problem.stop_reason) {
      const stop = document.createElement("p");
      stop.setAttribute("data-no-glossary", "");
      stop.textContent = `last resolved ${error.problem.last_resolved ?? "nothing"} · stopped because ${
        error.problem.stop_reason ?? "unknown"
      }`;
      element.appendChild(stop);
    }
  } else {
    element.textContent = String(error);
  }
  return element;
}
