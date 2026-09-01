/**
 * The committed glossary seed, read as the server's index endpoint would build it.
 *
 * A surface gate that invented its own term list would pass over a glossary that no longer
 * holds the words, so the rows come from `glossary_seed.yml` itself. The parser is line-based
 * because every field it needs is one line; `seedIsFlowStyle` is the guard that keeps that true.
 */
import { readFileSync } from "node:fs";

import type { GlossaryIndexPayload } from "../glossary/index.ts";

export const SEED_PATH = "../src/glasswell/seed/data/glossary_seed.yml";

export interface SeedTerm {
  term_id: string;
  term: string;
  aliases: string[];
  related_terms: string[];
  highlightable: boolean;
}

const ENTRY = /^- term: (.+)$/;
const LIST = /^ {2}(aliases|related_terms): \[(.*)\]$/;
const FLAG = /^ {2}highlightable: (true|false)$/;
const QUOTED = /^"[^"]*"(?:, "[^"]*")*$/;

/** The mirror of `glasswell.seed.glossary.slug`, which is what mints every `gt_*` id. */
export function slug(term: string): string {
  const body = term
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return `gt_${body}`;
}

export function loadSeed(path: string = SEED_PATH): SeedTerm[] {
  const terms: SeedTerm[] = [];
  for (const line of readFileSync(path, "utf8").split("\n")) {
    const start = ENTRY.exec(line);
    if (start?.[1]) {
      terms.push({
        term_id: slug(start[1]),
        term: start[1],
        aliases: [],
        related_terms: [],
        highlightable: true,
      });
      continue;
    }
    const current = terms[terms.length - 1];
    if (!current) continue;
    const list = LIST.exec(line);
    if (list?.[1]) {
      current[list[1] as "aliases" | "related_terms"] = [...(list[2] ?? "").matchAll(/"([^"]*)"/g)]
        .map((match) => match[1] ?? "");
      continue;
    }
    const flag = FLAG.exec(line);
    if (flag) current.highlightable = flag[1] === "true";
  }
  return terms;
}

/** Every `aliases:`/`related_terms:` line is a quoted flow list, so the parser reads them whole. */
export function seedIsFlowStyle(path: string = SEED_PATH): boolean {
  return readFileSync(path, "utf8")
    .split("\n")
    .filter((line) => /^ {2}(aliases|related_terms):/.test(line))
    .every((line) => {
      const list = LIST.exec(line);
      return list !== null && QUOTED.test((list[2] ?? "").trim());
    });
}

/** `get_glossary_index`'s rule: a non-highlightable term is served as stopwords, never entries. */
export function seedIndexPayload(terms: SeedTerm[]): GlossaryIndexPayload {
  const entries: GlossaryIndexPayload["entries"] = [];
  const stopwords: string[] = [];
  for (const row of terms) {
    const surfaces = [...new Set([row.term, ...row.aliases].map((one) => one.toLowerCase()))].sort();
    if (!row.highlightable) {
      stopwords.push(...surfaces);
      continue;
    }
    for (const surface of surfaces) {
      entries.push({ surface, term_id: row.term_id, n_words: surface.split(" ").length });
    }
  }
  entries.sort((left, right) => right.n_words - left.n_words || left.surface.localeCompare(right.surface));
  return {
    index_version: "gix_seed",
    entries,
    stopwords: [...new Set(stopwords)].sort(),
  };
}

/** What `/v1/glossary` serves the popover: enough for a hover, not the expanded definition. */
export function seedTermPayload(terms: SeedTerm[]): Record<string, unknown>[] {
  return terms.map((row) => ({
    term_id: row.term_id,
    term: row.term,
    aliases: row.aliases,
    short_definition: `${row.term}, as the seed defines it.`,
    domain_tags: [],
    highlightable: row.highlightable,
  }));
}
