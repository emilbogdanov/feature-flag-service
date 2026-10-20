import { evaluate, expect, projectName, test } from "./stack.ts";

test("a flag created and targeted in the dashboard is served as targeted", async ({
  signedIn: page,
  api,
  project,
}) => {
  const flag = { project, environment: "prod", flag: "dark-mode" };

  await page.getByRole("link", { name: projectName(project) }).click();
  await page.getByRole("link", { name: "New flag" }).click();
  await page.getByLabel("Name", { exact: true }).fill("Dark mode");
  await expect(page.getByLabel("Key", { exact: true })).toHaveValue("dark-mode");
  await page.getByRole("button", { name: "Create flag" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Dark mode" })).toBeVisible();

  // On in production for German users, off for everyone else.
  await page.getByRole("link", { name: "Edit targeting in Production" }).click();
  await page.getByLabel("On in Production").check();
  await page.getByRole("button", { name: "Add rule" }).click();
  const rule = page.getByRole("group", { name: "Rule 1", exact: true });
  await rule.getByLabel("Attribute").fill("country");
  await rule.getByLabel("Values, one per line").fill("DE");
  await page
    .getByRole("group", { name: "Everyone else" })
    .getByLabel("Variant", { exact: true })
    .selectOption("off");
  await page.getByRole("button", { name: "Save targeting for Production" }).click();
  await expect(page.getByText(/^Saved\./)).toBeVisible();

  expect(await evaluate(api, flag, { key: "user-1", attributes: { country: "DE" } })).toMatchObject(
    { variant: "on", reason: "rule_match", rule_id: "rule-1" },
  );
  expect(await evaluate(api, flag, { key: "user-2", attributes: { country: "FR" } })).toMatchObject(
    { variant: "off", reason: "fallthrough" },
  );

  // The kill switch, from the project's flag list.
  await page.getByRole("link", { name: projectName(project) }).click();
  const killSwitch = page.getByRole("switch", { name: "Dark mode in Production" });
  await expect(killSwitch).toBeChecked();
  await killSwitch.click();
  await expect(killSwitch).not.toBeChecked();
  expect(await evaluate(api, flag, { key: "user-1", attributes: { country: "DE" } })).toMatchObject(
    { variant: "off", reason: "disabled" },
  );

  // And each of those steps is in the project's history.
  await page.getByRole("link", { name: "Changes to this project" }).click();
  const changes = page.getByRole("region", { name: "Changes" }).getByRole("listitem");
  await expect(changes.first()).toContainText("turned off dark-mode in prod");
  await expect(changes.filter({ hasText: "changed the targeting of dark-mode" })).toHaveCount(1);
  await expect(changes.filter({ hasText: "created the flag dark-mode" })).toHaveCount(1);
});
