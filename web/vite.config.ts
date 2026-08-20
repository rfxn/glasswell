import { defineConfig } from "vitest/config";

// Tiles moved under /v1 (C11), so one proxy rule covers the API and the tile origin.
export default defineConfig({
  base: "/",
  // No source map: the bundle is served by StaticFiles, and this source is proprietary (M-6).
  // `npm run dev` is unaffected — esbuild maps the dev server's modules regardless.
  build: { outDir: "dist", target: "es2022", sourcemap: false },
  server: {
    proxy: {
      "/v1": { target: "http://127.0.0.1:8000", changeOrigin: false },
    },
  },
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
    coverage: { provider: "v8", reporter: ["text-summary"], include: ["src/**/*.ts"] },
  },
});
