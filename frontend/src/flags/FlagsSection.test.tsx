import { screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { serveStorefront, versionMismatch } from "../test/api";
import { ADMIN_KEY, newCheckout, switched } from "../test/fixtures";
import { renderDashboard } from "../test/render";
import { server } from "../test/server";

const SWITCH_PATH = "*/projects/storefront/flags/new-checkout/environments/:environment";

async function flagsTable() {
  const section = await screen.findByRole("region", { name: "Flags" });
  return within(section).findByRole("table");
}

describe("the flag list", () => {
  it("shows each flag with its state in every environment", async () => {
    serveStorefront();
    renderDashboard("/projects/storefront", { adminKey: ADMIN_KEY });

    const table = await flagsTable();
    expect(within(table).getByRole("link", { name: "New checkout" })).toHaveAttribute(
      "href",
      "/projects/storefront/flags/new-checkout",
    );
    expect(screen.getByRole("switch", { name: "New checkout in Development" })).toBeChecked();
    expect(screen.getByRole("switch", { name: "New checkout in Production" })).not.toBeChecked();
  });

  it("explains what a new flag does when there are none", async () => {
    serveStorefront([]);
    renderDashboard("/projects/storefront", { adminKey: ADMIN_KEY });

    expect(await screen.findByText("No flags yet.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New flag" })).toHaveAttribute(
      "href",
      "/projects/storefront/flags/new",
    );
  });
});

describe("switching a flag", () => {
  it("turns it on only if it is still the version on screen", async () => {
    serveStorefront();
    const sent: { path: string; ifMatch: string | null }[] = [];
    server.use(
      http.post(`${SWITCH_PATH}/enable`, ({ request }) => {
        sent.push({
          path: new URL(request.url).pathname,
          ifMatch: request.headers.get("If-Match"),
        });
        return HttpResponse.json(switched(newCheckout, "prod", true));
      }),
    );
    const { user } = renderDashboard("/projects/storefront", { adminKey: ADMIN_KEY });

    await flagsTable();
    await user.click(screen.getByRole("switch", { name: "New checkout in Production" }));

    expect(await screen.findByRole("switch", { name: "New checkout in Production" })).toBeChecked();
    expect(sent).toEqual([
      { path: "/projects/storefront/flags/new-checkout/environments/prod/enable", ifMatch: '"7"' },
    ]);
  });

  it("turns it off whatever changed meanwhile, as a kill switch must", async () => {
    serveStorefront();
    const ifMatch: (string | null)[] = [];
    server.use(
      http.post(`${SWITCH_PATH}/disable`, ({ request }) => {
        ifMatch.push(request.headers.get("If-Match"));
        return HttpResponse.json(switched(newCheckout, "dev", false));
      }),
    );
    const { user } = renderDashboard("/projects/storefront", { adminKey: ADMIN_KEY });

    await flagsTable();
    await user.click(screen.getByRole("switch", { name: "New checkout in Development" }));

    expect(
      await screen.findByRole("switch", { name: "New checkout in Development", checked: false }),
    ).toBeInTheDocument();
    expect(ifMatch).toEqual([null]);
  });

  it("explains a conflict and shows the flag as it is now", async () => {
    let listed = newCheckout;
    serveStorefront();
    server.use(
      http.get("*/projects/storefront/flags", () => HttpResponse.json([listed])),
      http.post(`${SWITCH_PATH}/enable`, () => {
        // Someone else turned it on first.
        listed = switched(newCheckout, "prod", true);
        return HttpResponse.json(versionMismatch, { status: 412 });
      }),
    );
    const { user } = renderDashboard("/projects/storefront", { adminKey: ADMIN_KEY });

    await flagsTable();
    await user.click(screen.getByRole("switch", { name: "New checkout in Production" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn't turn on New checkout in Production. Someone changed this flag",
    );
    expect(
      await screen.findByRole("switch", { name: "New checkout in Production", checked: true }),
    ).toBeInTheDocument();
  });
});
