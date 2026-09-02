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

export interface JurisdictionCensus {
  /** Canonical status id → wells measured in it across every registered jurisdiction. */
  readonly byStatus: Readonly<Record<string, number>>;
  /** Wells measured in total. Null when no jurisdiction has been measured yet. */
  readonly total: number | null;
  /** The most recent measurement date any jurisdiction carries, or null. */
  readonly measuredOn: string | null;
  /** True when the registry could not be read at all — never presented as an empty census. */
  readonly degraded: boolean;
}

interface CountFigure {
  readonly value?: string;
}

interface CensusRow {
  readonly well_count?: CountFigure | null;
  readonly well_counts_by_status?: readonly { status_canonical: string; wells: CountFigure }[];
  readonly measured_on?: string | null;
}

export const EMPTY_CENSUS: JurisdictionCensus = {
  byStatus: {},
  total: null,
  measuredOn: null,
  degraded: false,
};

const DEGRADED_CENSUS: JurisdictionCensus = { ...EMPTY_CENSUS, degraded: true };

let pending: Promise<JurisdictionCensus> | null = null;
let resident: JurisdictionCensus = EMPTY_CENSUS;

const figure = (value: CountFigure | null | undefined): number | null => {
  const parsed = Number(value?.value);
  return value?.value !== undefined && Number.isFinite(parsed) ? parsed : null;
};

export function censusOf(rows: readonly CensusRow[]): JurisdictionCensus {
  const byStatus: Record<string, number> = {};
  let total: number | null = null;
  let measuredOn: string | null = null;
  for (const row of rows) {
    const counted = figure(row.well_count);
    // Absent, not zero: a jurisdiction registered and not yet refreshed is not one with no
    // wells, and adding a zero for it would make the total read as if it had been measured.
    if (counted === null) continue;
    total = (total ?? 0) + counted;
    if (row.measured_on && (measuredOn === null || row.measured_on > measuredOn)) {
      measuredOn = row.measured_on;
    }
    for (const entry of row.well_counts_by_status ?? []) {
      const wells = figure(entry.wells);
      if (wells === null) continue;
      byStatus[entry.status_canonical] = (byStatus[entry.status_canonical] ?? 0) + wells;
    }
  }
  return { byStatus, total, measuredOn, degraded: false };
}

/** Fetch once per session. A refusal is a degraded census, never an empty one. */
export function loadCensus(): Promise<JurisdictionCensus> {
  pending ??= getEnvelope<readonly CensusRow[]>("/v1/jurisdictions")
    .then((envelope) => {
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

/** Test seam: the module holds one session's answer, and a suite runs many sessions. */
export function resetCensus(next: JurisdictionCensus = EMPTY_CENSUS): void {
  // A seeded census is a settled one, so `loadCensus()` resolves to it rather than reaching
  // for a fetch. Without this the pass that reads the census and the census itself could not
  // be exercised in one test, which is how both stayed green over the defect between them.
  pending = Promise.resolve(next);
  resident = next;
}
