/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API owns the paths at the root (/projects, /api-keys, /audit), so the dashboard lives under
// a prefix of its own. Behind one origin the two need no CORS and no path rewriting.
const apiUrl = process.env.FLAGSTAFF_API_URL ?? "http://localhost:8080";
const apiPaths = ["/projects", "/api-keys", "/audit"];

export default defineConfig({
  base: "/dashboard/",
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(apiPaths.map((path) => [path, apiUrl])),
  },
  test: {
    // The end-to-end tests in e2e/ run under Playwright, against the compose stack.
    include: ["src/**/*.test.{ts,tsx}"],
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
  },
});
