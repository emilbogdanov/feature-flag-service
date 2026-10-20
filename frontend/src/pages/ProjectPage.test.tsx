import { screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { expect, it } from "vitest";

import { ADMIN_KEY, storefront, storefrontEnvironments } from "../test/fixtures";
import { renderDashboard } from "../test/render";
import { server } from "../test/server";

it("shows the project's environments and their ruleset versions", async () => {
  server.use(
    http.get("*/projects/storefront", () => HttpResponse.json(storefront)),
    http.get("*/projects/storefront/environments", () => HttpResponse.json(storefrontEnvironments)),
  );
  renderDashboard("/projects/storefront", { adminKey: ADMIN_KEY });

  expect(await screen.findByRole("heading", { level: 1, name: "Storefront" })).toBeInTheDocument();
  const table = await screen.findByRole("table");
  const rows = within(table).getAllByRole("row").slice(1);
  expect(rows.map((row) => within(row).getAllByRole("cell")[1]?.textContent)).toEqual([
    "dev",
    "staging",
    "prod",
  ]);
  const development = within(table).getByRole("row", { name: /Development/ });
  expect(
    within(development)
      .getAllByRole("cell")
      .map((cell) => cell.textContent),
  ).toEqual(["Development", "dev", "12", expect.any(String)]);
});

it("says so when the project doesn't exist", async () => {
  const missing = { detail: "project 'nope' does not exist", code: "project_not_found" };
  server.use(
    http.get("*/projects/nope", () => HttpResponse.json(missing, { status: 404 })),
    http.get("*/projects/nope/environments", () => HttpResponse.json(missing, { status: 404 })),
  );
  renderDashboard("/projects/nope", { adminKey: ADMIN_KEY });

  expect(await screen.findByRole("heading", { name: "No such project" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "See all projects" })).toHaveAttribute("href", "/");
});

it("answers an unknown address with a page of its own", async () => {
  renderDashboard("/flags", { adminKey: ADMIN_KEY });

  expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
});
