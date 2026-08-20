import { clearKey, isKeyShaped, saveKey, storedKey } from "../api/client.ts";

export interface KeyPanelOptions {
  reason: "missing" | "rejected";
  onRetry(): void;
}

const COPY: Record<KeyPanelOptions["reason"], string> = {
  missing: "This deployment needs the owner key before it can serve anything.",
  rejected:
    "The stored key was rejected. It is still in this browser, so every request will keep" +
    " failing until it is replaced or cleared.",
};

/** UX P1-6: a wrong stored key used to leave devtools as the only way back into the app. */
export function keyPanel(options: KeyPanelOptions): HTMLElement {
  const panel = document.createElement("section");
  panel.className = "gw-key-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-labelledby", "gw-key-title");

  const head = document.createElement("header");
  head.className = "gw-panel-head";
  const heading = document.createElement("h2");
  heading.id = "gw-key-title";
  heading.tabIndex = -1;
  heading.textContent = options.reason === "rejected" ? "Owner key rejected" : "Owner key needed";
  head.appendChild(heading);

  const body = document.createElement("div");
  body.className = "gw-panel-body";

  const explain = document.createElement("p");
  explain.setAttribute("data-no-glossary", "");
  explain.textContent = COPY[options.reason];
  body.appendChild(explain);

  const form = document.createElement("form");
  form.className = "gw-key-form";

  const label = document.createElement("label");
  label.className = "gw-key-label";
  label.htmlFor = "gw-key-input";
  label.textContent = "Owner key";

  const input = document.createElement("input");
  input.type = "password";
  input.id = "gw-key-input";
  input.className = "gw-key-input";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.placeholder = "64 hex characters";
  input.setAttribute("aria-describedby", "gw-key-note");

  const use = document.createElement("button");
  use.type = "submit";
  use.className = "gw-key-use";
  use.textContent = "Use this key";

  form.append(label, input, use);
  body.appendChild(form);

  const note = document.createElement("p");
  note.id = "gw-key-note";
  note.className = "gw-key-note";
  note.setAttribute("role", "status");
  note.textContent = storedKey()
    ? "A key is stored in this browser. It is never shown back to you."
    : "No key is stored in this browser.";
  body.appendChild(note);

  const clear = document.createElement("button");
  clear.type = "button";
  clear.className = "gw-key-clear";
  clear.textContent = "Clear stored key";
  clear.addEventListener("click", () => {
    clearKey();
    note.textContent = "Stored key cleared. Enter a key above, or reopen the app with #key=…";
  });
  body.appendChild(clear);

  const hint = document.createElement("p");
  hint.className = "gw-key-hint";
  hint.setAttribute("data-no-glossary", "");
  hint.textContent = "The key travels in the fragment or this field — never in the query string.";
  body.appendChild(hint);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const candidate = input.value;
    if (!isKeyShaped(candidate)) {
      note.textContent = "That is not an owner key: it must be 64 hex characters.";
      input.focus();
      return;
    }
    saveKey(candidate);
    input.value = "";
    note.textContent = "Key stored. Retrying…";
    options.onRetry();
  });

  panel.append(head, body);
  return panel;
}
