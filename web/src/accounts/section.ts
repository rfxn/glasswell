/**
 * Accounts, as a section of Status rather than a fourth header mode: at 390 px the mode switch
 * spends 373 of the 390 px a phone has, and a fourth button needs 46 more than exist.
 *
 * Owner-only, and the role is the one `main.ts` already resolved — the section never probes for
 * it. Everything destructive states what ends before it ends, and every refusal is the server's
 * own sentence: a screen that rewrites a 422 in vaguer words is how a reader stops trusting it.
 */

import {
  ApiError,
  createUser,
  disableUser,
  enableUser,
  listSessions,
  listUsers,
  resetPassword,
  revokeSession,
  updateUser,
} from "../api/client.ts";
import type { MintedUser, SessionRecord, UserRecord } from "../api/client.ts";
import type { Envelope } from "../api/envelope.ts";
import { emptyState, warningNotes } from "../chrome/notes.ts";
import { labelElement } from "../glossary/gw-term.ts";
import { displayTime, element } from "../status-page/dom.ts";
import { confirmDialog } from "./confirm.ts";

const TITLE = "Accounts";
const ADD_USER = "Add user";
const USERS_EMPTY = "No accounts yet.";
const SESSIONS_EMPTY = "No sessions.";
const SHOWN_ONCE = "Copy this password. It is not shown again.";
const REVOKE_CONFIRM = "Revoke this session? They sign in again.";
const disableConfirm = (name: string): string => `Disable ${name}? Their sessions end now.`;
const resetConfirm = (name: string): string => `Reset ${name}'s password? Their sessions end now.`;

const ROLES = ["owner", "viewer"] as const;
const ROLE_TERMS: Record<string, string> = { owner: "gt_owner", viewer: "gt_viewer" };
const WHERE: Record<string, string> = { lan: "LAN", remote: "Remote", unknown: "Unknown" };

interface Slots {
  notice: HTMLElement;
  dialog: HTMLElement;
  create: HTMLElement;
  reveal: HTMLElement;
  body: HTMLElement;
}

/** Null for anyone but an owner: the section does not exist rather than rendering empty. */
export function accountsSection(role: string | null | undefined): HTMLElement | null {
  if (role !== "owner") return null;
  const section = element("section", "gw-status-section gw-accounts");
  section.id = "accounts";
  section.setAttribute("aria-labelledby", "gw-accounts-title");

  const head = element("div", "gw-status-section-head");
  const title = element("h2", "gw-status-section-title");
  title.id = "gw-accounts-title";
  title.textContent = TITLE;
  const add = document.createElement("button");
  add.type = "button";
  add.className = "gw-status-refresh gw-accounts-add";
  add.textContent = ADD_USER;
  head.append(title, add);

  const slots: Slots = {
    notice: element("div", "gw-accounts-notice"),
    dialog: element("div", "gw-accounts-dialog"),
    create: element("div", "gw-accounts-create"),
    reveal: element("div", "gw-accounts-reveal"),
    body: element("div", "gw-accounts-body"),
  };
  slots.notice.setAttribute("role", "status");
  section.append(head, slots.notice, slots.dialog, slots.create, slots.reveal, slots.body);
  add.addEventListener("click", () => openCreate(section));
  return section;
}

/** The two collections, fetched together: one owner action changes both. */
export async function loadAccounts(section: HTMLElement): Promise<void> {
  const body = slotsOf(section).body;
  try {
    const [users, sessions] = await Promise.all([listUsers(), listSessions()]);
    body.replaceChildren(usersTable(section, users), sessionsTable(section, sessions));
  } catch (error) {
    body.replaceChildren(refusal(error));
  }
  // `?view=status#accounts` names a section that does not exist until this resolves, so the
  // deep link has to be honoured here rather than by the browser's own hash handling.
  if (window.location.hash === `#${section.id}`) section.scrollIntoView?.();
}

function slotsOf(section: HTMLElement): Slots {
  const find = (name: string): HTMLElement =>
    section.querySelector<HTMLElement>(`.gw-accounts-${name}`) as HTMLElement;
  return {
    notice: find("notice"),
    dialog: find("dialog"),
    create: find("create"),
    reveal: find("reveal"),
    body: find("body"),
  };
}

function usersTable(section: HTMLElement, users: readonly UserRecord[]): HTMLElement {
  const wrap = element("div", "gw-status-table-wrap");
  if (users.length === 0) {
    wrap.append(emptyState(USERS_EMPTY));
    return wrap;
  }
  const table = element("table", "gw-status-table gw-accounts-users");
  const caption = document.createElement("caption");
  caption.textContent = "Users";
  table.append(caption, headRow([label("Name"), roleLabel(), label("Created"),
    label("Last sign-in"), sessionsLabel(), label("")]));

  const rows = document.createElement("tbody");
  for (const user of users) {
    const row = document.createElement("tr");
    row.dataset["user"] = user.username;
    const name = document.createElement("th");
    name.scope = "row";
    name.append(accountName(user.username));
    if (user.state === "disabled") name.append(state("Disabled"));
    row.append(
      name,
      cell(roleSelect(section, user)),
      cell(time(user.created_at)),
      cell(user.last_login_at ? time(user.last_login_at) : text("Never")),
      cell(text(String(user.sessions_live))),
      cell(userActions(section, user)),
    );
    rows.append(row);
  }
  table.append(rows);
  wrap.append(table);
  return wrap;
}

function sessionsTable(section: HTMLElement, sessions: readonly SessionRecord[]): HTMLElement {
  const wrap = element("div", "gw-status-table-wrap");
  if (sessions.length === 0) {
    wrap.append(emptyState(SESSIONS_EMPTY));
    return wrap;
  }
  const table = element("table", "gw-status-table gw-accounts-sessions");
  const caption = document.createElement("caption");
  caption.textContent = "Sessions";
  table.append(caption, headRow([label("User"), roleLabel(), label("Started"),
    label("Last seen"), label("Expires"), label("Client"), label("Where"), label("")]));

  const rows = document.createElement("tbody");
  for (const session of sessions) {
    const row = document.createElement("tr");
    row.dataset["session"] = session.session_id;
    const who = document.createElement("th");
    who.scope = "row";
    who.append(accountName(session.username));
    if (session.state !== "active") who.append(state(capitalise(session.state)));
    row.append(
      who,
      cell(labelElement(session.role, ROLE_TERMS[session.role] ?? null)),
      cell(time(session.created_at)),
      cell(time(session.last_seen_at)),
      cell(time(session.expires_at)),
      cell(text(session.user_agent_family)),
      cell(text(WHERE[session.address_class] ?? session.address_class)),
      cell(revokeButton(section, session)),
    );
    rows.append(row);
  }
  table.append(rows);
  wrap.append(table);
  return wrap;
}

function userActions(section: HTMLElement, user: UserRecord): HTMLElement {
  const actions = element("div", "gw-accounts-actions");
  const reset = action("Reset password", () =>
    ask(section, resetConfirm(user.username), "Reset password", () =>
      run(section, async () => reveal(section, await resetPassword(user.user_id))),
    ),
  );
  const toggle =
    user.state === "disabled"
      ? action("Enable", () => run(section, () => enableUser(user.user_id)))
      : action("Disable", () =>
          ask(section, disableConfirm(user.username), "Disable", () =>
            run(section, () => disableUser(user.user_id)),
          ),
        );
  actions.append(reset, toggle);
  return actions;
}

/**
 * gate-v076 N3: the pinned action column paints an opaque background over whatever slides under
 * it, and at 390 a long username's last glyphs ended 5 px inside that column -- chopped
 * mid-stroke with no ellipsis, on a row carrying `Disable`. A `td` ignores `max-width` under
 * auto table layout, so the constraint has to live on an element inside it. The full name stays
 * on the title, and the ellipsis is what says there is more.
 */
function accountName(username: string): HTMLElement {
  const name = element("span", "gw-accounts-name");
  name.textContent = username;
  name.title = username;
  return name;
}

function revokeButton(section: HTMLElement, session: SessionRecord): HTMLElement {
  const revoke = action("Revoke", () =>
    ask(section, REVOKE_CONFIRM, "Revoke", () =>
      run(section, () => revokeSession(session.session_id)),
    ),
  );
  revoke.disabled = session.state !== "active";
  return revoke;
}

function roleSelect(section: HTMLElement, user: UserRecord): HTMLElement {
  const select = document.createElement("select");
  select.className = "gw-accounts-role";
  select.setAttribute("aria-label", `Role for ${user.username}`);
  for (const role of ROLES) {
    const option = document.createElement("option");
    option.value = role;
    option.textContent = role;
    option.selected = role === user.role;
    select.append(option);
  }
  select.addEventListener("change", () => {
    void run(section, () => updateUser(user.user_id, select.value));
  });
  return select;
}

/** The create form, opened from the head button and closed by submitting or by opening again. */
function openCreate(section: HTMLElement): void {
  const slot = slotsOf(section).create;
  if (slot.hasChildNodes()) {
    slot.replaceChildren();
    return;
  }
  const form = document.createElement("form");
  form.className = "gw-accounts-form";

  const nameLabel = document.createElement("label");
  nameLabel.htmlFor = "gw-accounts-username";
  nameLabel.textContent = "Username";
  const name = document.createElement("input");
  name.id = "gw-accounts-username";
  name.name = "username";
  name.type = "text";
  name.required = true;
  name.spellcheck = false;
  name.autocomplete = "off";

  const roleLabelElement = document.createElement("label");
  roleLabelElement.htmlFor = "gw-accounts-role";
  roleLabelElement.textContent = "Role";
  const role = document.createElement("select");
  role.id = "gw-accounts-role";
  role.name = "role";
  for (const value of ROLES) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    option.selected = value === "viewer";
    role.append(option);
  }

  const submit = document.createElement("button");
  submit.type = "submit";
  submit.className = "gw-accounts-submit";
  submit.textContent = "Create";

  form.append(nameLabel, name, roleLabelElement, role, submit);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (submit.disabled) return;
    submit.disabled = true;
    void run(section, async () => {
      // No password is sent, so the one the server mints exists in this response and nowhere
      // else -- not in a URL, not in this form, and never in a second request.
      reveal(section, await createUser(name.value, role.value));
      slot.replaceChildren();
    }).finally(() => {
      submit.disabled = false;
    });
  });
  slot.replaceChildren(form);
  name.focus();
}

/**
 * The one screen a minted password appears on. `data-gw-secret` is the hook a screenshot
 * harness substitutes before it captures, so the visual gate never photographs a live
 * credential; dismissing drops the value out of the DOM entirely.
 */
function reveal(section: HTMLElement, minted: Envelope<MintedUser>): void {
  const slot = slotsOf(section).reveal;
  const password = minted.data.password;
  if (!password) {
    slot.replaceChildren();
    return;
  }
  const panel = element("div", "gw-accounts-secret");
  panel.setAttribute("role", "group");
  panel.setAttribute("aria-label", SHOWN_ONCE);

  const line = element("p", "gw-accounts-secret-line");
  line.setAttribute("data-no-glossary", "");
  line.textContent = SHOWN_ONCE;

  const value = document.createElement("code");
  value.className = "gw-accounts-secret-value";
  value.setAttribute("data-gw-secret", "");
  value.textContent = password;

  // The panel above says the password is not shown again, so a Copy that quietly does nothing
  // costs the reader the credential. `navigator.clipboard` is undefined in a non-secure
  // context — which the LAN host is, on plain http — and writeText rejects on a denied
  // permission or an unfocused document. Both say so here rather than to the console.
  const copied = element("span", "gw-accounts-copy-state");
  copied.setAttribute("role", "status");
  copied.setAttribute("data-no-glossary", "");
  const said = (outcome: string): void => {
    copied.textContent = outcome;
  };
  const copy = action("Copy", () => {
    const written = navigator.clipboard?.writeText(password);
    if (!written) {
      said("No clipboard on this connection. Select the value above.");
      return;
    }
    void written.then(
      () => said("Copied."),
      () => said("Copy refused. Select the value above."),
    );
  });
  const dismiss = action("Dismiss", () => slot.replaceChildren());

  const actions = element("div", "gw-accounts-secret-actions");
  actions.append(copy, dismiss, copied);
  panel.append(line, value, actions);
  // The server states the show-once rule in `meta.warnings`; the panel renders what it said
  // rather than a second sentence of its own.
  panel.append(...warningNotes(minted.meta.warnings ?? []));
  slot.replaceChildren(panel);
}

/** Every ending action states what ends, and nothing is sent until the reader says go. */
function ask(section: HTMLElement, message: string, verb: string, onConfirm: () => void): void {
  const slot = slotsOf(section).dialog;
  const dialog = confirmDialog({
    message,
    confirmLabel: verb,
    onConfirm: () => {
      slot.replaceChildren();
      onConfirm();
    },
    onCancel: () => slot.replaceChildren(),
  });
  slot.replaceChildren(dialog);
  slot.querySelector<HTMLButtonElement>(".gw-accounts-confirm-go")?.focus();
}

async function run(section: HTMLElement, act: () => Promise<unknown>): Promise<void> {
  const slots = slotsOf(section);
  slots.notice.replaceChildren();
  try {
    await act();
  } catch (error) {
    slots.notice.replaceChildren(refusal(error));
  }
  await loadAccounts(section);
}

/**
 * The server's own words. The card once caught a 422, replaced it with vaguer wording of its
 * own, and left the reader with no way to learn what the server had actually said.
 */
function refusal(error: unknown): HTMLElement {
  const panel = element("div", "gw-accounts-refusal");
  panel.setAttribute("data-no-glossary", "");
  const line = element("p", "gw-accounts-refusal-line");
  if (!(error instanceof ApiError)) {
    line.textContent = String(error);
    panel.append(line);
    return panel;
  }
  line.textContent = error.problem.detail ?? error.problem.title;
  panel.append(line);
  // Only when the server named fields: an empty list would print a bare bullet saying nothing.
  const pointers = error.problem.errors ?? [];
  if (pointers.length > 0) {
    const list = element("ul", "gw-accounts-refusal-fields");
    for (const failure of pointers) {
      const item = document.createElement("li");
      item.textContent = [failure.pointer, failure.detail ?? failure.code]
        .filter((part): part is string => Boolean(part))
        .join(" — ");
      list.append(item);
    }
    panel.append(list);
  }
  return panel;
}

function action(label: string, onClick: () => void): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "gw-accounts-action";
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

function headRow(cells: readonly Node[]): HTMLElement {
  const head = document.createElement("thead");
  const row = document.createElement("tr");
  for (const content of cells) {
    const header = document.createElement("th");
    header.scope = "col";
    header.append(content);
    row.append(header);
  }
  head.append(row);
  return head;
}

function cell(content: Node): HTMLTableCellElement {
  const output = document.createElement("td");
  output.append(content);
  return output;
}

function label(text: string): HTMLElement {
  const span = document.createElement("span");
  span.textContent = text;
  return span;
}

/** Two column headings carry a definition rather than a tooltip nobody wrote. */
function roleLabel(): HTMLElement {
  return labelElement("Role", "gt_role");
}

function sessionsLabel(): HTMLElement {
  return labelElement("Live sessions", "gt_session");
}

function text(value: string): HTMLElement {
  const span = document.createElement("span");
  span.textContent = value;
  return span;
}

function state(value: string): HTMLElement {
  const badge = element("span", "gw-accounts-state");
  badge.textContent = value;
  return badge;
}

function time(value: string): HTMLElement {
  const stamp = document.createElement("time");
  stamp.dateTime = value;
  stamp.textContent = displayTime(value);
  return stamp;
}

function capitalise(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}
