import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

/**
 * Every string literal a shipped module carries, with the file and line it sits on.
 *
 * Shared rather than written twice: v0.82's em-dash lint and the card track's own vocabulary
 * test both need the same reading of "a literal this build ships", and two extractors that
 * disagree are two gates that disagree.
 *
 * Comments are stripped before the scan. A note explaining why a class is called what it is
 * would otherwise redden the gate that exists to stop the class being called that in code.
 */
export interface ShippedLiteral {
  readonly file: string;
  readonly line: number;
  readonly value: string;
}

/**
 * What the scan excludes, by name rather than by file class.
 *
 * `\.generated\.ts$` stood here for one seed-derived fixture and covered every generated
 * module with it, including `jurisdictions.generated.ts`, which is imported by nine shipped
 * modules and carries five per-jurisdiction colours. A class of filenames chosen for a
 * test-support file is not a rule; the file it was chosen for is.
 */
export const EXCLUDED = [
  /\.test\.ts$/,
  /\/test\//,
  /fixtures?\.ts$/,
  /status-classes\.generated\.ts$/,
] as const;

const TEST_SUPPORT = (file: string): boolean => EXCLUDED.some((pattern) => pattern.test(file));

/** Comments, then literals: a `//` inside a string must not open one. */
export function stripComments(source: string): string {
  let out = "";
  let index = 0;
  while (index < source.length) {
    const char = source[index]!;
    if (char === '"' || char === "'" || char === "`") {
      const closed = readLiteral(source, index);
      out += source.slice(index, closed);
      index = closed;
      continue;
    }
    if (char === "/" && source[index + 1] === "/") {
      const end = source.indexOf("\n", index);
      index = end === -1 ? source.length : end;
      continue;
    }
    if (char === "/" && source[index + 1] === "*") {
      const end = source.indexOf("*/", index + 2);
      const skipped = source.slice(index, end === -1 ? source.length : end + 2);
      // Newlines kept, so a line number after a block comment is still the file's own.
      out += skipped.replace(/[^\n]/g, "");
      index = end === -1 ? source.length : end + 2;
      continue;
    }
    out += char;
    index += 1;
  }
  return out;
}

function readLiteral(source: string, start: number): number {
  const quote = source[start]!;
  let index = start + 1;
  while (index < source.length) {
    const char = source[index]!;
    if (char === "\\") {
      index += 2;
      continue;
    }
    if (char === quote) return index + 1;
    index += 1;
  }
  return source.length;
}

/** Every single- or double-quoted literal in one module, comments already removed. */
// A literal spelled as "\\u2014" renders the same character as one spelled with it, so the gates
// must see the character; the generic unescape below would have turned it into "u2014".
export function decodeUnicodeEscapes(raw: string): string {
  return raw.replace(/\\u\{([0-9a-fA-F]+)\}|\\u([0-9a-fA-F]{4})/g, (_m, braced: string | undefined, plain: string | undefined) =>
    String.fromCodePoint(parseInt((braced ?? plain) as string, 16)),
  );
}

export function literalsIn(file: string, source: string): ShippedLiteral[] {
  const stripped = stripComments(source);
  const found: ShippedLiteral[] = [];
  let line = 1;
  let index = 0;
  while (index < stripped.length) {
    const char = stripped[index]!;
    if (char === "\n") {
      line += 1;
      index += 1;
      continue;
    }
    if (char === '"' || char === "'") {
      const end = readLiteral(stripped, index);
      const raw = stripped.slice(index + 1, end - 1);
      found.push({ file, line, value: decodeUnicodeEscapes(raw).replace(/\\(.)/g, "$1") });
      line += stripped.slice(index, end).split("\n").length - 1;
      index = end;
      continue;
    }
    index += 1;
  }
  return found;
}

/**
 * Template literals, on the same comment-stripped source `literalsIn` reads.
 *
 * `literalsIn` extracts quoted strings only, and the card's prose is largely backticked
 * (`peer.ts`'s caption, `card.ts`'s coverage line), so a quoted-only corpus would miss the
 * sentences most at risk of making a claim. R-6's fold: the card's vocabulary gate reads it
 * from here rather than declaring its own, so one module decides what a shipped literal is.
 */
export function templatesIn(file: string, source: string): ShippedLiteral[] {
  const stripped = stripComments(source);
  const found: ShippedLiteral[] = [];
  for (const match of stripped.matchAll(/`(?:\\[\s\S]|[^`\\])*`/g)) {
    found.push({
      file,
      line: stripped.slice(0, match.index).split("\n").length,
      value: match[0].slice(1, -1),
    });
  }
  return found;
}

function walk(directory: string, out: string[]): string[] {
  for (const entry of readdirSync(directory)) {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) walk(path, out);
    else if (path.endsWith(".ts")) out.push(path);
  }
  return out;
}

/**
 * The modules that import one module, resolved by path rather than by matching the specifier.
 *
 * `web/src/chrome/header.ts` imports `./status.ts` and that is a different module, the session
 * chrome: a scanner that matched the string would pull in a file holding "expired" and
 * "required" and re-create the problem the scope exists to solve.
 */
export function importersOf(root: string, target: string): string[] {
  const wanted = resolve(target);
  const found: string[] = [];
  for (const file of walk(root, [])) {
    const source = stripComments(readFileSync(file, "utf8"));
    const specifiers = [...source.matchAll(/from\s+"([^"]+)"/g)].map((match) => match[1]!);
    const resolved = specifiers
      .filter((specifier) => specifier.startsWith("."))
      .map((specifier) => resolve(join(file, "..", specifier)));
    if (resolved.includes(wanted)) found.push(file);
  }
  return found;
}

/** The importer set plus the named extras, test support excluded. Sorted, so a diff is stable. */
export function scannedFiles(
  root: string,
  target: string,
  extras: readonly string[] = [],
): string[] {
  const scoped = new Set([...importersOf(root, target), resolve(target), ...extras.map((extra) => resolve(extra))]);
  return [...scoped].filter((file) => !TEST_SUPPORT(file)).sort();
}

/** Every literal the scoped set ships, ready to be compared against what the wire serves. */
export function shippedLiterals(files: readonly string[]): ShippedLiteral[] {
  return files.flatMap((file) => literalsIn(file, readFileSync(file, "utf8")));
}
