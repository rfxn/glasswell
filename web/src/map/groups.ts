/**
 * The reader's taxonomy for the layer list. The tile marts group by the source that publishes
 * a layer; an engineer reads by what the layer is *of*, which is this. Kept out of
 * registry.ts because tests/e2e/chrome-fold.mjs parses that file by splitting on
 * two-space-indented braces, and a second object table there would parse as layers.
 */
export type LayerGroupId = "spine" | "land" | "derived" | "geology";

export interface LayerGroup {
  id: LayerGroupId;
  label: string;
}

/**
 * Listed in the order the panel renders. The two framework groups sit under the spine because
 * that is the reading order, and geology is last because its rows are the ones a build may
 * ship with no source behind them.
 */
export const LAYER_GROUPS: readonly LayerGroup[] = [
  { id: "spine", label: "Well spine" },
  { id: "land", label: "Land and legal framework" },
  { id: "derived", label: "Derived surfaces" },
  { id: "geology", label: "Geology framework" },
];

const BY_ID = new Map(LAYER_GROUPS.map((group) => [group.id, group]));

export function layerGroup(id: LayerGroupId): LayerGroup | undefined {
  return BY_ID.get(id);
}
