import { expect, test } from "./stack.ts";

// An instance trusts a key it has checked for 10 s, so a revoke may take that long to reach
// whichever instance answers.
const KEY_CACHE_MS = 10_000;

test("an SDK key issued in the dashboard reads rules until it is revoked there", async ({
  signedIn: page,
  playwright,
  baseURL,
  project,
}) => {
  const name = `${project}-reader`;

  await page.getByRole("link", { name: "API keys" }).click();
  await page.getByRole("link", { name: "Issue a key" }).click();
  await page.getByLabel("Name", { exact: true }).fill(name);
  await page.getByLabel("Project", { exact: true }).selectOption(project);
  await page.getByLabel("Environment", { exact: true }).selectOption("prod");
  await page.getByRole("button", { name: "Issue key" }).click();
  const secret = await page.getByLabel("Secret").inputValue();
  expect(secret).toMatch(/^fs_sdk_/);

  const sdk = await playwright.request.newContext({
    ...(baseURL !== undefined && { baseURL }),
    extraHTTPHeaders: { Authorization: `Bearer ${secret}` },
  });
  expect((await sdk.get("/sdk/ruleset")).status()).toBe(200);

  await page.getByRole("link", { name: "Done" }).click();
  await page.getByRole("button", { name: `Revoke ${name}`, exact: true }).click();
  await page.getByRole("button", { name: `Revoke ${name} now` }).click();
  await expect(page.getByRole("row", { name: new RegExp(name) })).toContainText("Revoked");

  await expect
    .poll(async () => (await sdk.get("/sdk/ruleset")).status(), { timeout: KEY_CACHE_MS + 5_000 })
    .toBe(401);
  await sdk.dispose();
});
