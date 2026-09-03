import { beforeEach } from "vitest";

import { SEEDED_STATUS_CLASSES } from "../map/status-classes.generated.ts";
import { setStatusVocabulary } from "../map/status.ts";

/**
 * Every suite starts with the vocabulary served, because every surface under test runs after
 * `loadCensus()` has settled in the browser. A suite that needs the unresolved store asks for
 * it with `resetStatusVocabulary()`, which is the state one test in `status-vocabulary.test.ts`
 * and one in `legend.test.ts` are specifically about.
 */
// At import as well as before each case: a setup file is evaluated before the suites are, and
// a suite that reads the vocabulary at module scope -- a `const everyStatus` beside its
// describe -- would otherwise see the empty store the hook has not run for yet.
setStatusVocabulary(SEEDED_STATUS_CLASSES);

beforeEach(() => {
  setStatusVocabulary(SEEDED_STATUS_CLASSES);
});
