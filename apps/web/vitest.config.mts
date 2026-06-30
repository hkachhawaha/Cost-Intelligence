import path from "path";

import { defineConfig } from "vitest/config";

// `@/…` resolves to the app root (mirrors tsconfig paths). esbuild uses the automatic JSX
// runtime so component tests need no explicit React import. Default node env; component tests
// render server-side via react-dom/server (no browser/jsdom needed).
export default defineConfig({
  resolve: { alias: { "@": path.resolve(__dirname, ".") } },
  esbuild: { jsx: "automatic" },
  test: { environment: "node", globals: true },
});
