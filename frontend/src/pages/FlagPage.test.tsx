import { screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { serveStorefront } from "../test/api";
import { ADMIN_KEY, newCheckout } from "../test/fixtures";
import { renderDashboard } from "../test/render";
import { server } from "../test/server";

const FLAG_PATH = "/projects/storefront/flags/new-checkout";

describe("a flag's page", () => {
  it("shows how each environment serves the flag, and its variants", async () => {
    serveStorefront();
    renderDashboard(FLAG_PATH, { adminKey: ADMIN_KEY });

    expect(await screen.findByRole("heading", { level: 1, name: "New checkout" })).toBeVisible();
    expect(screen.getByText("The one-page checkout.")).toBeVisible();
    const environments = within(screen.getByRole("region", { name: "Environments" }));
    const development = await environments.findByRole("row", { name: /Development/ });
    expect(
      within(development)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ).toEqual(["On", "off", "1", "on 25%, off 75%"]);
    const variants = within(screen.getByRole("region", { name: "Variants" }));
    expect(variants.getByRole("row", { name: /^on/ })).toHaveTextContent("true");
  });

  it("says so when there is no such flag", async () => {
    serveStorefront();
    server.use(
      http.get("*/projects/storefront/flags/gone", () =>
        HttpResponse.json(
          { detail: "flag 'gone' does not exist", code: "flag_not_found" },
          { status: 404 },
        ),
      ),
    );
    renderDashboard("/projects/storefront/flags/gone", { adminKey: ADMIN_KEY });

    expect(await screen.findByRole("heading", { name: "No such flag" })).toBeVisible();
  });

  it("shows an archived flag without anything to change", async () => {
    serveStorefront([{ ...newCheckout, archived_at: "2026-10-05T09:00:00Z" }]);
    renderDashboard(FLAG_PATH, { adminKey: ADMIN_KEY });

    expect(await screen.findByText(/^Archived on/)).toBeVisible();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).toHaveTextContent("Sign out");
  });
});
