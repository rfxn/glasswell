/**
 * The served ND snapshot every panel coverage statement is computed from — one place, so
 * two rows can never disagree about the denominator and a percentage is never hand-written.
 * The numbers are read from the deployed mart at the named refresh, not from the source
 * FeatureServer: the map draws the mart, so the mart's count is the honest denominator
 * (the FeatureServer's own vintage total, 43,824, lives in the R8 rules that cite it).
 * Update all of it together at the next data-refresh sweep, from the refresh it names.
 */
export const ND_SNAPSHOT = {
  wells: 43_817,
  disposal: 1_989,
  traced: 525,
  /** marts.nd_wells_tile refresh the counts were read from (VM 111 mart at v0.37+dd49f63, read 2026-08-22). */
  refresh: "drv_gh5zhnea4trtofypofbq",
} as const;

/**
 * The served PLSS land snapshot, same discipline: promoted grid units per
 * cr_blm_plss_publisher_1 and the metric cells binned over them (M2-3).
 */
export const LAND_SNAPSHOT = {
  townships: 2_057,
  sections: 71_455,
  /** 1,152 township + 12,800 section rows in marts.land_metrics_tile. */
  cells: 13_952,
  /** marts.land_metrics_tile refresh the cell count was read from (VM 111 mart at v0.37+dd49f63, read 2026-08-22). */
  refresh: "drv_u6ntpnulcqf7kfij3t5a",
} as const;

const NUMBER = new Intl.NumberFormat("en-US");

/** "1,989 of 43,817 wells (4.5%)" — numerator, the snapshot denominator, computed share. */
export function ndCoverage(part: number): string {
  const percent = ((part / ND_SNAPSHOT.wells) * 100).toFixed(1);
  return `${NUMBER.format(part)} of ${NUMBER.format(ND_SNAPSHOT.wells)} wells (${percent}%)`;
}

export function ndWellCount(): string {
  return NUMBER.format(ND_SNAPSHOT.wells);
}

export function landCellCount(): string {
  return NUMBER.format(LAND_SNAPSHOT.cells);
}
