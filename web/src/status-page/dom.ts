/** The two helpers the Status surface and the Accounts section it mounts both need.

`accounts/section.ts` took them from `surface.ts`, which imports the section back, so the two
modules formed an import cycle. They live here instead: no cycle, and the section still stamps
a time the way the page around it does.
*/

/** A tagged element with a class, the shape three private copies in the tree already had. */
export function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className: string,
): HTMLElementTagNameMap[K] {
  const created = document.createElement(tag);
  created.className = className;
  return created;
}

/** A vintage stays as filed; an instant reads as UTC, which is the clock the product keeps. */
export function displayTime(value: string): string {
  if (/^\d{4}-\d{2}(-\d{2})?$/.test(value)) return value;
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) return value;
  return parsed.toISOString().replace("T", " ").replace(/:\d{2}\.\d{3}Z$/, " UTC");
}
