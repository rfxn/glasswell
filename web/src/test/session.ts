/**
 * The harness statement that a suite runs signed in. The real cookie is `__Host-gw_session`,
 * HttpOnly, so no test can forge it and no client code can read it — what these suites
 * actually rely on is their stubbed fetch answering, and this marker says so in one place.
 */
const MARKER = "gw_session_harness";

export function seedSession(): void {
  document.cookie = `${MARKER}=1; path=/`;
}

export function clearSession(): void {
  document.cookie = `${MARKER}=; path=/; max-age=0`;
}
