import { defineConfig, devices } from "@playwright/test";

// The end-to-end tests drive the dashboard in the compose stack, the way someone would use it,
// and check what they did through the API. See e2e/stack.ts for what they need.
export default defineConfig({
  testDir: "e2e",
  // They share one stack, and each makes a project of its own, so they can run side by side.
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.FLAGSTAFF_STACK_URL ?? "http://localhost:8080",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
