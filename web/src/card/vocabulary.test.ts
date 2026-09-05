import { readFileSync, readdirSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { isAbsolute, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { SEED_PATH } from "../test/glossary-seed.ts";
import { EXCLUDED, literalsIn, stripComments, type ShippedLiteral } from "../test/literals.ts";

/**
 * The vocabulary gate: what glasswell ships must never read as a reserves, resource, inventory
 * or EUR claim, and the sentence that says the quantiles are not the reserves convention must
 * still be on the card.
 *
 * It replaces `grep -rniE '\breserves?\b|\bEUR\b' web/src/`, which returns 8 on `main` with no
 * card work done and 12 on this branch — every one of the twelve a test name, a code comment or
 * a CSS comment using the verb "reserve", none of them a claim. A gate an engineer can only pass
 * by deleting live regression tests is not a gate; this reads shipped string literals, which is
 * the only text a reader ever sees.
 */

const SRC = fileURLToPath(new URL("..", import.meta.url));

function walk(directory: string, out: string[] = []): string[] {
  for (const entry of readdirSync(directory)) {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) walk(path, out);
    else if (path.endsWith(".ts")) out.push(path);
  }
  return out;
}

const shippedFiles = (): string[] =>
  walk(SRC).filter((file) => !EXCLUDED.some((pattern) => pattern.test(file)));

/**
 * Template literals, read with the shared module's comment stripper and added to what it
 * extracts: `literalsIn` reads quoted strings only, and the card's prose is largely backticked
 * (`peer.ts`'s caption, `card.ts`'s coverage line), so a quoted-only corpus would miss the
 * sentences most at risk of making a claim. The stripping — the half where two gates must not
 * disagree — is the shared one. R-6's fold takes the union.
 */
function templatesIn(file: string, source: string): ShippedLiteral[] {
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

const corpus = (): ShippedLiteral[] =>
  shippedFiles().flatMap((file) => {
    const source = readFileSync(file, "utf8");
    return [...literalsIn(file, source), ...templatesIn(file, source)];
  });

/**
 * The noun, not the verb. Each row is the claim and the qualifier that makes it one: "reserves"
 * behind a reserves category, "resource" in its petroleum sense, "inventory" counted in wells or
 * locations, and `EUR` as an uppercase token beside a volume unit. The verb "reserves" — a
 * column reserving width, a colour reserved for selection — is not a claim and is not matched.
 */
const CLAIMS: readonly [string, RegExp][] = [
  ["a reserves category", /\b(proved|probable|possible|remaining)\s+reserves\b/i],
  ["a resource claim", /\b(unrisked|recoverable|in[ -]place|petroleum|hydrocarbon|oil|gas)\s+resources?\b/i],
  ["a resource claim", /\bresources?\s+(potential|base|estimate|assessment|density)\b/i],
  [
    "a drilling-inventory claim",
    /\b(drilling|drilled|undrilled|remaining|net|gross|well|wells|location|locations|slot|slots|opportunit(y|ies)|tier|tiers)\s+inventor(y|ies)\b/i,
  ],
  ["a drilling-inventory claim", /\binventor(y|ies)\s+of\s+(wells|locations|slots)\b/i],
];

const VOLUME_UNIT = /\b(bbl|mbbl|mmbbl|boe|mboe|mmboe|mcf|mmcf|bcf|tcf|kft)\b/i;

/** `EUR` uppercase and beside a volume unit; the euro, and `EUROPE` in an operator name, are not. */
function eurClaim(value: string): boolean {
  for (const match of value.matchAll(/(?<![A-Za-z])EUR(?![A-Za-z])/g)) {
    const window = value.slice(Math.max(0, match.index - 16), match.index + 19);
    if (VOLUME_UNIT.test(window)) return true;
  }
  return false;
}

/**
 * The bare nouns a shipped literal already carries, each with the reason it is not a claim, so a
 * new one has to be argued for rather than merged. This is the ratchet the claim patterns above
 * cannot be: they read the petroleum sense, and these six read the infrastructure one. Measured
 * on `main` at e0e1213 and unchanged by the card group.
 */
const NOT_A_CLAIM: readonly [string, string][] = [
  ["Inventory", "the API rail's link to SB-04 §4.5's ingest-run inventory"],
  ["/v1/inventory/runs", "that endpoint's path: runs and manifests, not locations"],
  [
    "the resource. A collection puts its array here, never inside an items wrapper.",
    "REST's noun for a response body, in the envelope pane's own field guide",
  ],
  [
    "Checking infrastructure and dataset inventory…",
    "the status page counting datasets while they load",
  ],
  [
    "Resident inventory by storage layer, each row on its own stated grain",
    "bytes resident in PostgreSQL, captioned as storage",
  ],
  ["No dataset inventory was served.", "the same table's empty state"],
];

const NEAR = /\breserves?\b|\bresources?\b|\binventor(y|ies)\b|(?<![A-Za-z])EUR(?![A-Za-z])/i;

const where = (literal: ShippedLiteral): string =>
  `${literal.file.slice(SRC.length)}:${literal.line} ${JSON.stringify(literal.value.slice(0, 120))}`;

describe("what the card is allowed to call things", () => {
  it("reads a corpus large enough to be a gate", () => {
    // A scanner that resolves nothing passes every assertion below it. This is the floor that
    // says the corpus was actually read: the shipped tree is 100+ modules and thousands of
    // literals, and an extractor that returns a handful has broken rather than found nothing.
    const files = shippedFiles();
    const literals = corpus();
    expect(files.length, "the shipped module set collapsed").toBeGreaterThan(60);
    expect(literals.length, "the literal corpus collapsed").toBeGreaterThan(2_000);
    expect(files.some((file) => file.endsWith("/card/peer.ts"))).toBe(true);
    expect(files.every((file) => !file.endsWith(".test.ts"))).toBe(true);
  });

  it("ships no reserves, resource, inventory or EUR claim", () => {
    // The measured baseline: 0 on `main` at e0e1213 and 0 here. The delta is what this asserts.
    const offenders = corpus().flatMap((literal) => {
      const matched = CLAIMS.filter(([, pattern]) => pattern.test(literal.value)).map(
        ([what]) => what,
      );
      if (eurClaim(literal.value)) matched.push("an EUR claim");
      return matched.map((what) => `${what}: ${where(literal)}`);
    });
    expect(offenders, offenders.join("\n")).toHaveLength(0);
  });

  it("keeps every bare use of the four nouns on the list that says why it is not a claim", () => {
    const allowed = new Set(NOT_A_CLAIM.map(([value]) => value));
    const unexplained = corpus()
      .filter((literal) => NEAR.test(literal.value) && !allowed.has(literal.value))
      .map(where);
    expect(
      unexplained,
      `a shipped literal uses one of the four nouns and is not on NOT_A_CLAIM:\n${unexplained.join("\n")}`,
    ).toHaveLength(0);
    expect(NOT_A_CLAIM.every(([, reason]) => reason.length > 20)).toBe(true);
  });

  it("keeps the quantile convention on the card, which is where the negation is read", () => {
    // The sentence itself is served, not authored here: `/quantile_convention` resolves the
    // glossary term below. What the client owes is the row that carries it, so deleting the
    // disclaimer fails this gate exactly as adding a claim does.
    const peer = corpus().filter((literal) => literal.file.endsWith("/card/peer.ts"));
    const values = peer.map((literal) => literal.value);
    expect(values, "the peer facts dropped the quantile convention").toContain(
      "Quantile convention",
    );
    expect(values, "the quantile convention lost its served label").toContain(
      "/quantile_convention",
    );
  });

  it("resolves the glossary seed from the module, not from the process CWD", () => {
    // The gate reads the seed to prove the served definition is still a negation. A
    // CWD-relative path makes that pass only under `npm --prefix web run test`; run from the
    // repository root, or by an editor, it is an ENOENT and the negation goes unchecked.
    expect(isAbsolute(SEED_PATH), `${SEED_PATH} is resolved against the process CWD`).toBe(true);
    const cwd = process.cwd();
    try {
      process.chdir(tmpdir());
      expect(() => readFileSync(SEED_PATH, "utf8")).not.toThrow();
    } finally {
      process.chdir(cwd);
    }
  });

  it("keeps the served definition a negation of the reserves convention", () => {
    const seed = readFileSync(SEED_PATH, "utf8");
    const start = seed.indexOf("- term: Quantile convention");
    expect(start, "the glossary no longer seeds the quantile convention").toBeGreaterThan(-1);
    const end = seed.indexOf("\n- term: ", start + 1);
    const entry = seed.slice(start, end === -1 ? undefined : end);
    expect(entry, "the definition no longer says which convention it is not").toMatch(
      /opposite of the reserves convention/i,
    );
    expect(entry, "the definition no longer says what P10 means there").toMatch(
      /P10 is the high case/i,
    );
  });

  it("leaves the two registry guards M-1 named standing", () => {
    // The failure mode the raw grep created: an engineer reads "the word appears once" as an
    // instruction and deletes the two assertions that a tile subtitle does not say reserve.
    const registry = readFileSync(join(SRC, "map/registry.test.ts"), "utf8");
    expect(registry).toContain("not.toMatch(/reserve|resource/i)");
    expect(registry).toContain("not.toMatch(/saltwater|reserves/i)");
  });
});
