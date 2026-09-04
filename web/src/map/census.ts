/**
 * The wells census, fetched rather than pinned.
 *
 * Four undated maps in `status.ts` used to say how many wells each class held. They were
 * measured by hand against the deployed database and carried no date, so a legend read from
 * them was a claim about whenever somebody last looked. `/v1/jurisdictions` serves the same
 * counts with the derivation that produced them and the date they were measured on, so this
 * asks for them once per session and says which of the three states it is in — loading,
 * measured, or degraded — rather than substituting a zero for any of them.
 *
 * Off the entry path by construction: the map chunk is the only importer, and the fetch is
 * behind `loadCensus()` rather than run at module scope.
 */
import { getEnvelope } from "../api/client.ts";
import { setStatusVocabulary } from "./status.ts";

/** One jurisdiction's measurement: the count, the handle that resolves it, and its date. */
export interface JurisdictionFigure {
  readonly wells: number;
  readonly handle: string | null;
  readonly measuredOn: string | null;
}

export interface JurisdictionCensus {
  /**
   * Each registration's served status vocabulary. The legend's per-jurisdiction sentence is
   * read from here rather than from the generated module, which is what §3.1(a) put it on the
   * wire for: a note can change without a rebuild. The generated module keeps the presentation
   * facts the layer panel needs before this fetch settles (R-4), and
   * `test_jurisdiction_parity.py` holds the pair equal.
   */
  readonly vocabularies: readonly JurisdictionVocabulary[];
  /** Canonical status id → wells measured in it across every registered jurisdiction. */
  readonly byStatus: Readonly<Record<string, number>>;
  /** Registered code → that jurisdiction's own measurement. Absent until one is served. */
  readonly byJurisdiction: Readonly<Record<string, JurisdictionFigure>>;
  /** Wells measured in total. Null when no jurisdiction has been measured yet. */
  readonly total: number | null;
  /** The most recent measurement date any jurisdiction carries, or null. */
  readonly measuredOn: string | null;
  /** True when the registry could not be read at all — never presented as an empty census. */
  readonly degraded: boolean;
  /**
   * Whether the registry has answered at all. `total` cannot carry this: it is null both
   * before the fetch and after one that measured nothing anywhere, and a surface that reads
   * the first as the second claims an absence about a question nobody has finished asking.
   */
  readonly resolved: boolean;
}

interface CountFigure {
  readonly value?: string;
  /** The derivation handle, spelled as the envelope spells it. */
  readonly d?: string;
}

/** One registration's served status vocabulary, as `/v1/jurisdictions` spells it. */
interface ServedVocabulary {
  readonly rule_id?: string;
  readonly resolved_at?: string | null;
  readonly unmapped_action?: string | null;
  readonly classes?: readonly string[];
  readonly legend_note?: string | null;
}

interface CensusRow {
  readonly jurisdiction_code?: string;
  readonly well_count?: CountFigure | null;
  readonly well_counts_by_status?: readonly { status_canonical: string; wells: CountFigure }[];
  readonly measured_on?: string | null;
  readonly vocabulary?: ServedVocabulary | null;
}

/** What one registration's vocabulary says, keyed by the rule the legend classes a view by. */
export interface JurisdictionVocabulary {
  readonly code: string;
  readonly rule: string;
  readonly resolvedAt: string | null;
  readonly unmappedAction: string | null;
  readonly classes: readonly string[];
  readonly legendNote: string | null;
}

export const EMPTY_CENSUS: JurisdictionCensus = {
  vocabularies: [],
  byStatus: {},
  byJurisdiction: {},
  total: null,
  measuredOn: null,
  degraded: false,
  resolved: false,
};

// Resolved: a refusal is an answer, and the surfaces that say so need to know it arrived.
const DEGRADED_CENSUS: JurisdictionCensus = { ...EMPTY_CENSUS, degraded: true, resolved: true };

let pending: Promise<JurisdictionCensus> | null = null;
let resident: JurisdictionCensus = EMPTY_CENSUS;

const figure = (value: CountFigure | null | undefined): number | null => {
  const parsed = Number(value?.value);
  return value?.value !== undefined && Number.isFinite(parsed) ? parsed : null;
};

export function censusOf(rows: readonly CensusRow[]): JurisdictionCensus {
  const vocabularies: JurisdictionVocabulary[] = [];
  const byStatus: Record<string, number> = {};
  const byJurisdiction: Record<string, JurisdictionFigure> = {};
  let total: number | null = null;
  let measuredOn: string | null = null;
  for (const row of rows) {
    // Read before the count guard: a registration with no measurement yet still has a
    // vocabulary, and the legend's sentence about it does not wait on a refresh.
    if (row.jurisdiction_code && row.vocabulary?.rule_id) {
      vocabularies.push({
        code: row.jurisdiction_code,
        rule: row.vocabulary.rule_id,
        resolvedAt: row.vocabulary.resolved_at ?? null,
        unmappedAction: row.vocabulary.unmapped_action ?? null,
        classes: [...(row.vocabulary.classes ?? [])],
        legendNote: row.vocabulary.legend_note ?? null,
      });
    }
    const counted = figure(row.well_count);
    // Absent, not zero: a jurisdiction registered and not yet refreshed is not one with no
    // wells, and adding a zero for it would make the total read as if it had been measured.
    if (counted === null) continue;
    total = (total ?? 0) + counted;
    if (row.jurisdiction_code) {
      byJurisdiction[row.jurisdiction_code] = {
        wells: counted,
        handle: row.well_count?.d ?? null,
        measuredOn: row.measured_on ?? null,
      };
    }
    if (row.measured_on && (measuredOn === null || row.measured_on > measuredOn)) {
      measuredOn = row.measured_on;
    }
    for (const entry of row.well_counts_by_status ?? []) {
      const wells = figure(entry.wells);
      if (wells === null) continue;
      byStatus[entry.status_canonical] = (byStatus[entry.status_canonical] ?? 0) + wells;
    }
  }
  return {
    vocabularies,
    byStatus,
    byJurisdiction,
    total,
    measuredOn,
    degraded: false,
    resolved: true,
  };
}

/** Fetch once per session. A refusal is a degraded census, never an empty one. */
export function loadCensus(): Promise<JurisdictionCensus> {
  pending ??= getEnvelope<readonly CensusRow[]>("/v1/jurisdictions")
    .then((envelope) => {
      // The same one fetch seeds the status vocabulary. It rides in `meta` because the domain
      // is not a jurisdiction, and it is seeded before the census is returned so that every
      // surface awaiting this promise finds a resolved store rather than a race.
      setStatusVocabulary(envelope.meta?.status_classes ?? []);
      resident = censusOf(envelope.data ?? []);
      return resident;
    })
    .catch(() => {
      resident = DEGRADED_CENSUS;
      return resident;
    });
  return pending;
}

/** What has been fetched so far. `EMPTY_CENSUS` until `loadCensus()` settles. */
export function census(): JurisdictionCensus {
  return resident;
}

/**
 * Wells measured in one canonical class. Null where nothing has measured it: while the census
 * is unknown, and for a class the census carries no row for. A `?? 0` here read the second as
 * "the registry measured none of these", which is a claim the registry never made — and it
 * hid the class 68,186 Texas wells are in (v0.76 D1).
 */
export function measuredWellCount(id: string): number | null {
  if (resident.total === null) return null;
  return resident.byStatus[id] ?? null;
}

/** Every served vocabulary. Empty until `/v1/jurisdictions` answers, and empty when it refuses. */
export function servedVocabularies(): readonly JurisdictionVocabulary[] {
  return resident.vocabularies;
}

/** One jurisdiction's measured well count, or null where the registry has served none. */
export function measuredJurisdiction(code: string): JurisdictionFigure | null {
  return resident.byJurisdiction[code] ?? null;
}

/** Test seam: the module holds one session's answer, and a suite runs many sessions. */
export function resetCensus(next: JurisdictionCensus = EMPTY_CENSUS): void {
  // A seeded census is a settled one, so `loadCensus()` resolves to it rather than reaching
  // for a fetch. Without this the pass that reads the census and the census itself could not
  // be exercised in one test, which is how both stayed green over the defect between them.
  pending = Promise.resolve(next);
  resident = next;
}
