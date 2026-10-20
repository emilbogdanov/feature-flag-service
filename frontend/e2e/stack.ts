import { type APIRequestContext, type Page, expect, test as base } from "@playwright/test";

import type { EvaluationResponse } from "../src/api/schema.ts";

// The stack's admin key, from flagstaff-server create-admin-key; CI makes one for each run.
function adminKey(): string {
  const key = process.env.FLAGSTAFF_ADMIN_KEY;
  if (key === undefined || key === "") {
    throw new Error("Set FLAGSTAFF_ADMIN_KEY to an admin key for the stack under test");
  }
  return key;
}

interface Fixtures {
  // The API as an admin, for setting up and for checking what the dashboard did.
  api: APIRequestContext;
  // A project only this test uses, since the stack keeps its data between runs.
  project: string;
  // The dashboard, signed in with the admin key.
  signedIn: Page;
}

export const test = base.extend<Fixtures>({
  api: async ({ playwright, baseURL }, use) => {
    const api = await playwright.request.newContext({
      ...(baseURL !== undefined && { baseURL }),
      extraHTTPHeaders: { Authorization: `Bearer ${adminKey()}` },
    });
    await use(api);
    await api.dispose();
  },
  project: async ({ api }, use, testInfo) => {
    const key = `e2e-${testInfo.workerIndex.toString()}-${Date.now().toString(36)}`;
    const created = await api.post("/projects", { data: { key, name: projectName(key) } });
    expect(created.status()).toBe(201);
    await use(key);
  },
  // After the project exists, so the project list loaded on signing in has it.
  signedIn: async ({ page, project }, use) => {
    await page.goto("/");
    await page.getByLabel("Admin key").fill(adminKey());
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Projects" })).toBeVisible();
    await expect(page.getByRole("link", { name: projectName(project) })).toBeVisible();
    await use(page);
  },
});

export { expect } from "@playwright/test";

export function projectName(key: string): string {
  return `End to end ${key}`;
}

// What the API says a user gets from a flag, by the same engine every SDK runs.
export async function evaluate(
  api: APIRequestContext,
  path: { project: string; environment: string; flag: string },
  context: { key: string; attributes?: Record<string, string | number | boolean> },
): Promise<EvaluationResponse | undefined> {
  const response = await api.post(
    `/projects/${path.project}/environments/${path.environment}/evaluate`,
    { data: { context, flags: [path.flag] } },
  );
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as { evaluations: Record<string, EvaluationResponse> };
  return body.evaluations[path.flag];
}
