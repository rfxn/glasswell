/**
 * The confirmation the three ending actions open. `window.confirm` is not an option: it cannot
 * be styled, cannot carry the sentence that says what ends, and blocks the event loop while a
 * request is the thing being decided about.
 */

export interface ConfirmOptions {
  /** What ends, in one sentence, in the reader's terms. */
  message: string;
  /** The verb on the button that goes ahead, so the button says what it does. */
  confirmLabel: string;
  onConfirm(): void;
  onCancel(): void;
}

export function confirmDialog(options: ConfirmOptions): HTMLElement {
  const dialog = document.createElement("div");
  dialog.className = "gw-accounts-confirm";
  dialog.setAttribute("role", "alertdialog");
  dialog.setAttribute("aria-label", options.message);

  const message = document.createElement("p");
  message.className = "gw-accounts-confirm-line";
  message.setAttribute("data-no-glossary", "");
  message.textContent = options.message;

  const actions = document.createElement("div");
  actions.className = "gw-accounts-confirm-actions";
  const confirm = button(options.confirmLabel, "gw-accounts-confirm-go");
  const cancel = button("Cancel", "gw-accounts-confirm-cancel");
  confirm.addEventListener("click", () => options.onConfirm());
  cancel.addEventListener("click", () => options.onCancel());
  // Escape is the same answer as Cancel: a dialog a keyboard cannot dismiss is a trap.
  dialog.addEventListener("keydown", (event) => {
    if (event.key === "Escape") options.onCancel();
  });
  actions.append(confirm, cancel);

  dialog.append(message, actions);
  return dialog;
}

function button(label: string, className: string): HTMLButtonElement {
  const element = document.createElement("button");
  element.type = "button";
  element.className = className;
  element.textContent = label;
  return element;
}
