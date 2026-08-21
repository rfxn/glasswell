import type { AppState } from "../app/state.ts";

export interface ExplorerHooks {
  commit(next: Partial<AppState>, mode?: "push" | "replace"): void;
}

/**
 * C0 stub. The seam commit needs a real module behind `import("./explore/shell.ts")` so the
 * dispatch typechecks and the frozen files are edited once; C6 replaces the body.
 */
export async function mountExplorer(
  host: HTMLElement,
  state: AppState,
  _hooks: ExplorerHooks,
): Promise<void> {
  host.setAttribute("data-tab", state.tab);
}
