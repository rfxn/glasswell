import { ApiError, login } from "../api/client.ts";
import type { Session } from "../api/client.ts";

export interface LoginPanelOptions {
  reason: "required" | "expired";
  onSignedIn(session: Session): void;
}

const COPY: Record<LoginPanelOptions["reason"], { title: string; explain: string }> = {
  required: { title: "Sign in", explain: "This deployment serves nothing until you sign in." },
  expired: {
    title: "Sign in again",
    explain: "That session has ended. Signing in again returns you to the same view.",
  },
};

/** One sentence for every refusal: naming the field that was wrong enumerates accounts. */
const REFUSED = "That username and password were not accepted.";
/** No Retry-After echo — the wait would say which bucket fired, per-account or per-address. */
const THROTTLED = "Too many attempts. Wait a little, then try again.";
const UNREACHABLE = "The service could not be reached. Try again.";

export function loginPanel(options: LoginPanelOptions): HTMLElement {
  const panel = document.createElement("section");
  panel.className = "gw-login-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-labelledby", "gw-login-title");

  const head = document.createElement("header");
  head.className = "gw-panel-head";
  const heading = document.createElement("h2");
  heading.id = "gw-login-title";
  heading.tabIndex = -1;
  heading.textContent = COPY[options.reason].title;
  head.appendChild(heading);

  const body = document.createElement("div");
  body.className = "gw-panel-body";

  const explain = document.createElement("p");
  explain.setAttribute("data-no-glossary", "");
  explain.textContent = COPY[options.reason].explain;
  body.appendChild(explain);

  // No `action`: the app's own CSP ships `form-action 'none'`, so a native POST is blocked by
  // our own policy. The <form> and its autocomplete attributes are what password managers read.
  const form = document.createElement("form");
  form.className = "gw-login-form";

  const username = field({
    id: "gw-login-user",
    name: "username",
    label: "Username",
    type: "text",
    autocomplete: "username",
  });
  const password = field({
    id: "gw-login-pass",
    name: "password",
    label: "Password",
    type: "password",
    autocomplete: "current-password",
  });

  const submit = document.createElement("button");
  submit.type = "submit";
  submit.className = "gw-login-submit";
  submit.textContent = "Sign in";

  form.append(username.label, username.input, password.label, password.input, submit);
  body.appendChild(form);

  const note = document.createElement("p");
  note.id = "gw-login-note";
  note.className = "gw-login-note";
  note.setAttribute("role", "status");
  note.setAttribute("data-no-glossary", "");
  body.appendChild(note);
  username.input.setAttribute("aria-describedby", note.id);
  password.input.setAttribute("aria-describedby", note.id);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (submit.disabled) return;
    submit.disabled = true;
    note.textContent = "Signing in…";
    void login(username.input.value, password.input.value)
      .then((session) => {
        password.input.value = "";
        note.textContent = "Signed in.";
        options.onSignedIn(session);
      })
      .catch((error: unknown) => {
        password.input.value = "";
        note.textContent = messageFor(error);
        password.input.focus();
      })
      .finally(() => {
        submit.disabled = false;
      });
  });

  panel.append(head, body);
  return panel;
}

function messageFor(error: unknown): string {
  if (!(error instanceof ApiError)) return UNREACHABLE;
  if (error.problem.status === 429) return THROTTLED;
  return REFUSED;
}

interface FieldSpec {
  id: string;
  name: string;
  label: string;
  type: "text" | "password";
  autocomplete: AutoFill;
}

function field(spec: FieldSpec): { label: HTMLLabelElement; input: HTMLInputElement } {
  const label = document.createElement("label");
  label.className = "gw-login-label";
  label.htmlFor = spec.id;
  label.textContent = spec.label;

  const input = document.createElement("input");
  input.type = spec.type;
  input.id = spec.id;
  input.name = spec.name;
  input.className = "gw-login-input";
  input.autocomplete = spec.autocomplete;
  input.required = true;
  input.spellcheck = false;
  return { label, input };
}
