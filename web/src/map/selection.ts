export interface FeatureRef {
  source: string;
  sourceLayer: string;
  id: string;
}

export interface SelectionGateway {
  hasSource(source: string): boolean;
  set(reference: FeatureRef): void;
  remove(reference: FeatureRef): void;
}

export interface Selection {
  select(api10: string | null): void;
  /** Sources arrive after the selection does on a deep link, and again after a style swap. */
  resync(): void;
  /** A replaced style takes every feature state with it; this is not a removal. */
  forget(): void;
}

/**
 * The selected well, tracked as writes rather than as intent.
 *
 * MapLibre's `removeFeatureState` for a feature it holds no coalesced state for indexes
 * `undefined` inside `SourceFeatureState.coalesceChanges` and throws out of `Map._render`,
 * which stops the frame loop. So the record kept here is of what was written into the map,
 * not of what the reader picked: the two diverge whenever a selection lands before the style's
 * sources exist, or survives a `setStyle` that replaced them.
 */
export function createSelection(
  refsFor: (api10: string) => FeatureRef[],
  gateway: SelectionGateway,
): Selection {
  let wanted: string | null = null;
  let written: FeatureRef[] = [];
  let complete = true;

  function paint(): void {
    for (const reference of written) {
      if (gateway.hasSource(reference.source)) gateway.remove(reference);
    }
    written = [];
    if (wanted === null) {
      complete = true;
      return;
    }
    const references = refsFor(wanted);
    for (const reference of references) {
      if (!gateway.hasSource(reference.source)) continue;
      gateway.set(reference);
      written.push(reference);
    }
    complete = written.length === references.length;
  }

  return {
    select(api10) {
      wanted = api10;
      paint();
    },
    // `styledata` fires on every setFilter and setLayoutProperty, which the zoom handler issues
    // per layer per frame of a pinch, so the settled case has to cost two field reads.
    resync() {
      if (complete) return;
      paint();
    },
    forget() {
      written = [];
      complete = wanted === null;
    },
  };
}
