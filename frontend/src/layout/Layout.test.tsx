import { screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { expect, it } from "vitest";

import { serveStorefront } from "../test/api";
import { ADMIN_KEY } from "../test/fixtures";
import { renderDashboard } from "../test/render";
import { server } from "../test/server";

it("marks the section the page belongs to", async () => {
  serveStorefront();
  renderDashboard("/projects/storefront/flags/new-checkout", { adminKey: ADMIN_KEY });

  const sections = within(await screen.findByRole("navigation", { name: "Sections" }));
  expect(sections.getByRole("link", { name: "Projects" })).toHaveAttribute("aria-current", "page");
  expect(sections.getByRole("link", { name: "API keys" })).not.toHaveAttribute("aria-current");
});

it("goes from one section to another", async () => {
  server.use(
    http.get("*/projects", () => HttpResponse.json([])),
    http.get("*/api-keys", () => HttpResponse.json([])),
  );
  const { user, router } = renderDashboard("/", { adminKey: ADMIN_KEY });

  await user.click(await screen.findByRole("link", { name: "API keys" }));

  expect(await screen.findByRole("heading", { level: 1, name: "API keys" })).toBeVisible();
  expect(router.state.location.pathname).toBe("/api-keys");
});
