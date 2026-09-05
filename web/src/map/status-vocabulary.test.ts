import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { EXCLUDED, scannedFiles, shippedLiterals } from "../test/literals.ts";
import { JURISDICTION_LIST } from "./jurisdictions.generated.ts";
import { SEEDED_STATUS_CLASSES } from "./status-classes.generated.ts";
import { STATUS_VOCAB_RULES, resetStatusVocabulary, setStatusVocabulary, statusVocabulary } from "./status.ts";

/**
 * The exit this track is judged on: no class name, label, colour, note or vocabulary rule id is
 * a literal any shipped module carries.
 *
 * Scoped to the modules that import the vocabulary plus the card's chip, because that is
 * exactly the set that can hold one: a module that does not import the vocabulary is not
 * restating it. The unscoped grep returns ten unrelated matches -- a session state, an auth
 * reason, a dataset group, a card flag label and a comment -- and chasing those would be a
 * list of exemptions rather than a rule.
 */
const ROOT = resolve(__dirname, "..");
const TARGET = resolve(__dirname, "status.ts");
// The card's chip, which imports the vocabulary through the card rather than through the map;
// and the generated registry module, which imports nothing and is imported by nine shipped
// modules, so a class id emitted into it by a future regen would ship unscanned.
const EXTRAS = [
  resolve(__dirname, "..", "card", "status-chip.ts"),
  resolve(__dirname, "jurisdictions.generated.ts"),
];

/**
 * A class colour is also a jurisdiction colour on five registrations, and that is a different
 * axis: `map_colour` predicts which class a jurisdiction's wells are mostly in, so it is drawn
 * FROM the palette rather than restating a class. A literal that is a registered map colour is
 * therefore not a restatement; anything else that equals a class colour is, unless it is named.
 */
const REGISTERED_MAP_COLOURS = new Set(JURISDICTION_LIST.map((row) => row.colour));

/**
 * The same reasoning for a rule id. The generated registry module is the registry's own copy,
 * rendered from the seed and held to the wire by `test_jurisdiction_parity.py` under R-4's
 * "keep both and gate them": a rule id in it is a registration's datum, not a hand-written
 * search key. What rule 3 exists to stop is a module deciding which regulator owns a class,
 * which is a literal typed by a person into code the registry never rendered.
 */
const REGISTERED_RULE_IDS = new Set(
  JURISDICTION_LIST.flatMap((row) => Object.values(row.rules)),
);

const served = () => [...SEEDED_STATUS_CLASSES];

function scanned(): string[] {
  return scannedFiles(ROOT, TARGET, EXTRAS);
}

function offenders(files: readonly string[], wanted: ReadonlySet<string>) {
  return shippedLiterals(files).filter((literal) => wanted.has(literal.value));
}

beforeEach(() => {
  setStatusVocabulary(served());
});

afterEach(() => {
  resetStatusVocabulary();
});

describe("the scoped set", () => {
  it("is the vocabulary's importers plus two named extras, test support excluded", () => {
    const files = scanned().map((file) => file.slice(ROOT.length + 1));

    expect(files).toEqual([
      "card/status-chip.ts",
      "map/census.ts",
      "map/counts.ts",
      "map/hover-card.ts",
      "map/jurisdictions.generated.ts",
      "map/legend.ts",
      "map/map.ts",
      "map/registry.ts",
      "map/status.ts",
      "map/style.ts",
      "map/swatch.ts",
    ]);
  });

  it("excludes only what it names, so the scope can be reconstructed from the rule", () => {
    // The recipe before exclusions is the importer set plus the two extras; what comes out is
    // stated here rather than left to a regex nobody reads beside the number it produces.
    const before = [
      ...new Set([
        ...scanned(),
        resolve(__dirname, "status-classes.generated.ts"),
        resolve(ROOT, "test", "surfaces.ts"),
        resolve(ROOT, "test", "vocabulary-setup.ts"),
      ]),
    ];
    const excluded = before.filter((file) => EXCLUDED.some((pattern) => pattern.test(file)));

    expect(before).toHaveLength(14);
    expect(excluded.map((file) => file.slice(ROOT.length + 1)).sort()).toEqual([
      "map/status-classes.generated.ts",
      "test/surfaces.ts",
      "test/vocabulary-setup.ts",
    ]);
    expect(EXCLUDED.map(String)).toEqual([
      "/\\.test\\.ts$/",
      "/\\/test\\//",
      "/fixtures?\\.ts$/",
      "/status-classes\\.generated\\.ts$/",
    ]);
  });
});

describe("no shipped literal restates the served vocabulary", () => {
  it("names no class id", () => {
    const ids = new Set(served().map((row) => row.status_canonical));

    expect(offenders(scanned(), ids)).toEqual([]);
  });

  it("names no class label or note", () => {
    const prose = new Set(served().flatMap((row) => [row.label, row.note]));

    expect(offenders(scanned(), prose)).toEqual([]);
  });

  it("names no class colour that is not a registered jurisdiction colour", () => {
    const colours = new Set(served().map((row) => row.colour));
    // The rule, not a list: a literal that is a registered `map_colour` is a palette value on
    // the jurisdiction axis and does not follow a class that changes colour. Five in the
    // generated registry are exactly that, and they are excused by being registered rather than
    // by being written down here.
    const found = offenders(scanned(), colours).filter(
      (literal) => !REGISTERED_MAP_COLOURS.has(literal.value),
    );

    // What is left is one line colour that is neither a class nor a registration: the North
    // Dakota spacing-unit label, drawn in the same grey as the `permitted` swatch. Named with
    // its reason, and filed against BRAND.md where the palette is decided.
    expect(
      found.map((literal) => `${literal.file.slice(ROOT.length + 1)}:${literal.value}`),
    ).toEqual(["map/registry.ts:#9FB0BC"]);
    expect([...REGISTERED_MAP_COLOURS].filter((colour) => colours.has(colour)).sort()).toEqual([
      "#3FA55E",
      "#7C8B96",
    ]);
  });

  it("names no registered status-vocabulary rule id outside the generated registry", () => {
    // What stops a family search coming back as a string search: the rule a class cites is the
    // registry's answer, and a literal here would be this file deciding which regulator owns it.
    const rules = new Set(STATUS_VOCAB_RULES);
    const found = offenders(scanned(), rules).filter(
      (literal) => !REGISTERED_RULE_IDS.has(literal.value),
    );

    expect(found).toEqual([]);
    // Not vacuous: the generated module does carry them, and it is in the scanned set.
    expect(offenders(scanned(), rules)).toHaveLength(STATUS_VOCAB_RULES.length);
  });

  it("leaves the class domain out of every shipped module", () => {
    // The generated fixture is seed-derived test support. A shipped import of it would be the
    // second copy the domain exists to remove, carrying neither a rule id nor an effective date.
    const importers = shippedLiterals(scanned()).filter((literal) =>
      literal.value.includes("status-classes.generated"),
    );

    expect(importers).toEqual([]);
  });
});

describe("the scanner is not blind", () => {
  let scratch = "";

  beforeEach(() => {
    scratch = mkdtempSync(join(tmpdir(), "gw-literals-"));
  });

  afterEach(() => {
    rmSync(scratch, { recursive: true, force: true });
  });

  function plant(body: string): string[] {
    // A copy of the shape, never the tree: the negative fixture is planted in a module that
    // imports the vocabulary, so the resolver finds it the way it finds a real importer.
    mkdirSync(join(scratch, "map"), { recursive: true });
    writeFileSync(join(scratch, "map", "status.ts"), "export const x = 1;\n", "utf8");
    writeFileSync(
      join(scratch, "map", "planted.ts"),
      `import { x } from "./status.ts";\n${body}\nexport const y = x;\n`,
      "utf8",
    );
    return scannedFiles(scratch, join(scratch, "map", "status.ts"));
  }

  it("catches a planted class id", () => {
    const files = plant('export const id = "plugged";');
    const ids = new Set(served().map((row) => row.status_canonical));

    expect(offenders(files, ids)).toHaveLength(1);
  });

  it("catches a planted label", () => {
    const files = plant('export const label = "Dry hole";');
    const labels = new Set(served().map((row) => row.label));

    expect(offenders(files, labels)).toHaveLength(1);
  });

  it("catches a planted colour", () => {
    const files = plant('export const colour = "#666A71";');
    const colours = new Set(served().map((row) => row.colour));

    expect(offenders(files, colours)).toHaveLength(1);
  });

  it("catches a planted vocabulary rule id", () => {
    const files = plant(`export const rule = "${STATUS_VOCAB_RULES[0]}";`);
    const rules = new Set(STATUS_VOCAB_RULES);

    expect(offenders(files, rules)).toHaveLength(1);
  });

  it("reads a literal inside a comment as a comment", () => {
    const files = plant('// the "plugged" class is drawn struck\nexport const z = 1;');
    const ids = new Set(served().map((row) => row.status_canonical));

    expect(offenders(files, ids)).toEqual([]);
  });
});

describe("gate (c): what the map renders is what the domain serves", () => {
  it("holds the seed's classes, in the seed's order, with its symbology", () => {
    const rendered = statusVocabulary();

    expect(rendered.map((status) => status.id)).toEqual(
      served().map((row) => row.status_canonical),
    );
    for (const [index, status] of rendered.entries()) {
      const row = served()[index]!;
      expect(status.label).toBe(row.label);
      expect(status.colour).toBe(row.colour);
      expect(status.glyph).toBe(row.glyph);
      expect(status.minZoom).toBe(row.min_zoom);
      expect(status.sortOrder).toBe(row.sort_order);
      expect(status.isAbsence).toBe(row.is_absence);
      expect(status.note).toBe(row.note);
      expect(status.rule).toBe(row.rule_id);
    }
  });

  it("draws nothing at all before the domain is served", () => {
    resetStatusVocabulary();

    expect(statusVocabulary()).toEqual([]);
  });
});
