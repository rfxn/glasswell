/**
 * The reader's chrome preferences. A privacy-mode browser throws on `localStorage` access
 * itself, not only on write, so both directions are guarded: a remembered theme or a
 * dismissed hint is worth keeping and never worth failing a boot over.
 */

export function readSetting(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null; // Storage blocked entirely; the caller falls back to its default.
  }
}

export function writeSetting(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Quota or a blocked store: the choice holds for this session and does not survive a reload.
  }
}
