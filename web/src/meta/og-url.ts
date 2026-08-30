/**
 * Open Graph consumers — Slack, iMessage, Discord, crawlers — do not reliably resolve a
 * relative `og:image`, so the card silently breaks the day the app is public. The origin is
 * configuration (`GLASSWELL_PUBLIC_ORIGIN`), never a literal: a hostname compiled into the
 * source is wrong for every deployment but one.
 */

export const PUBLIC_ORIGIN_ENV = "GLASSWELL_PUBLIC_ORIGIN";

/** The properties whose values must be absolute to survive an unfurl. */
export const ABSOLUTE_META_PROPERTIES = ["og:image", "twitter:image"] as const;

/**
 * An absolute URL when the origin is configured, and the path untouched when it is not.
 * Unset is the LAN deployment: a root-relative URL is merely useless to an unfurler, where
 * a guessed absolute one is actively wrong.
 */
export function absoluteMetaUrl(path: string, origin: string | undefined | null): string {
  const base = normalizeOrigin(origin);
  if (base === null || /^[a-z][a-z0-9+.-]*:/i.test(path)) return path;
  try {
    return new URL(path, base).toString();
  } catch {
    return path;
  }
}

/** `https://host` or `http://host`, trailing slash and path stripped; anything else is unset. */
export function normalizeOrigin(origin: string | undefined | null): string | null {
  const raw = (origin ?? "").trim();
  if (raw === "") return null;
  try {
    const parsed = new URL(raw);
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return null;
    return parsed.origin;
  } catch {
    return null;
  }
}

/**
 * Rewrites the `content` of every `ABSOLUTE_META_PROPERTIES` tag in an HTML document.
 * A document with none — which is this branch until the card tags land — comes back unchanged.
 */
export function absolutizeMetaUrls(html: string, origin: string | undefined | null): string {
  if (normalizeOrigin(origin) === null) return html;
  return html.replace(/<meta\b[^>]*>/gi, (tag) => {
    const property = /\b(?:property|name)\s*=\s*["']([^"']+)["']/i.exec(tag)?.[1];
    if (!property || !(ABSOLUTE_META_PROPERTIES as readonly string[]).includes(property)) {
      return tag;
    }
    return tag.replace(
      /(\bcontent\s*=\s*["'])([^"']*)(["'])/i,
      (_whole, open: string, value: string, close: string) =>
        `${open}${absoluteMetaUrl(value, origin)}${close}`,
    );
  });
}
