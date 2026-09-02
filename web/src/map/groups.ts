/**
 * The reader's taxonomy for the layer list. The tile marts group by the source that publishes
 * a layer; an engineer reads by what the layer is *of*, which is this — the groups, and the
 * families nested inside them. Both tables are kept out of registry.ts because
 * tests/e2e/chrome-fold.mjs parses that file by splitting on two-space-indented braces, and a
 * second object table there would parse as layers.
 */
export type LayerGroupId = "spine" | "land" | "derived" | "geology";

export interface LayerGroup {
  id: LayerGroupId;
  label: string;
}

/**
 * Listed in the order the panel renders. The two framework groups sit under the spine because
 * that is the reading order, and geology is last because its rows draw underneath everything
 * else on the canvas and are the ones a reader reaches for least.
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

export type LayerFamilyId = "wells";

/**
 * A nested set inside a group: rows that are the same layer from different filers, governed by
 * one parent switch. The parent is derived from its children at render time and is never a
 * layer — it declares no style layer, holds no id in the persisted set, and carries no swatch,
 * because four regulators' dots are four colours and one mark would predict a canvas three of
 * them contradict.
 */
export interface LayerFamily {
  id: LayerFamilyId;
  label: string;
  /** What the parent says while its children are shut. */
  subtitle: string;
  /** Names the axis the children divide on, so the disclosure says what opening it buys. */
  childAxis: string;
}

export const LAYER_FAMILIES: readonly LayerFamily[] = [
  {
    id: "wells",
    label: "Wells",
    subtitle:
      "Surface hole locations as each state's regulator filed them · one point per well ·" +
      " open this row to draw a state on its own",
    childAxis: "state",
  },
];

const FAMILY_BY_ID = new Map(LAYER_FAMILIES.map((family) => [family.id, family]));

export function layerFamily(id: LayerFamilyId): LayerFamily | undefined {
  return FAMILY_BY_ID.get(id);
}
