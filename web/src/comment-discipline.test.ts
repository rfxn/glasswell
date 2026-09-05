import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// Paths are relative to `web/`, which is vitest's cwd (the chrome/*.test.ts precedent).
const ROOT = "src";

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) return sources(path);
    return path.endsWith(".ts") ? [path] : [];
  });
}

describe("a docblock describes the declaration under it", () => {
  it("stacks no docblock on another with no declaration between them", () => {
    // gate H-32: `chart.ts` carried the key element's line above `keyStates`, and `stateKey`
    // twenty lines below had none. Four more in the tree had the same shape. It is the vestige
    // of a move, it always leaves one declaration undocumented and another described by the
    // wrong prose, and `tsc` cannot see it — so it is asserted rather than swept again next
    // round. A blank line between the two is the separator that makes a file header a header.
    const offenders = sources(ROOT).filter((path) =>
      readFileSync(path, "utf8").includes("*/\n/**"),
    );

    expect(offenders, `stacked docblocks in ${offenders.join(", ")}`).toEqual([]);
  });
});
