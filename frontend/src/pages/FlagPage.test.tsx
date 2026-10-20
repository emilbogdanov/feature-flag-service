import { screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import type { ChangeFlagDetails } from "../api/schema";
import { serveStorefront, versionMismatch } from "../test/api";
import { ADMIN_KEY, edited, newCheckout } from "../test/fixtures";
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

describe("editing a flag's name and description", () => {
  it("saves them against the version on screen", async () => {
    serveStorefront();
    const sent: { body: ChangeFlagDetails; ifMatch: string | null }[] = [];
    server.use(
      http.patch(`*${FLAG_PATH}`, async ({ request }) => {
        const body = (await request.json()) as ChangeFlagDetails;
        sent.push({ body, ifMatch: request.headers.get("If-Match") });
        return HttpResponse.json(edited(newCheckout, body));
      }),
    );
    const { user } = renderDashboard(FLAG_PATH, { adminKey: ADMIN_KEY });

    await user.click(await screen.findByRole("button", { name: "Edit name and description" }));
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "One-page checkout");
    await user.click(screen.getByRole("button", { name: "Save name and description" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "One-page checkout" }),
    ).toBeVisible();
    expect(sent).toEqual([
      {
        body: { name: "One-page checkout", description: "The one-page checkout." },
        ifMatch: '"7"',
      },
    ]);
  });

  it("keeps the edit on screen when someone else changed the flag first", async () => {
    serveStorefront();
    server.use(
      http.patch(`*${FLAG_PATH}`, () => HttpResponse.json(versionMismatch, { status: 412 })),
    );
    const { user } = renderDashboard(FLAG_PATH, { adminKey: ADMIN_KEY });

    await user.click(await screen.findByRole("button", { name: "Edit name and description" }));
    await user.type(screen.getByLabelText("Name"), " v2");
    await user.click(screen.getByRole("button", { name: "Save name and description" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Someone changed this flag");
    expect(screen.getByLabelText("Name")).toHaveValue("New checkout v2");
  });
});

describe("archiving a flag", () => {
  it("asks first, then archives it and goes back to the project", async () => {
    serveStorefront();
    const ifMatch: (string | null)[] = [];
    server.use(
      http.post(`*${FLAG_PATH}/archive`, ({ request }) => {
        ifMatch.push(request.headers.get("If-Match"));
        return HttpResponse.json(edited(newCheckout, { archived_at: "2026-10-20T09:00:00Z" }));
      }),
    );
    const { user, router } = renderDashboard(FLAG_PATH, { adminKey: ADMIN_KEY });

    await user.click(await screen.findByRole("button", { name: "Archive flag" }));
    expect(ifMatch).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Archive New checkout for good" }));

    await screen.findByRole("heading", { level: 1, name: "Storefront" });
    expect(router.state.location.pathname).toBe("/projects/storefront");
    expect(ifMatch).toEqual(['"7"']);
  });
});
