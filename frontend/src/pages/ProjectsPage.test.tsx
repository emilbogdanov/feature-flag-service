import { screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { expect, it } from "vitest";

import { ADMIN_KEY, billing, storefront } from "../test/fixtures";
import { renderDashboard } from "../test/render";
import { server } from "../test/server";

it("lists every project", async () => {
  server.use(http.get("*/projects", () => HttpResponse.json([storefront, billing])));
  renderDashboard("/", { adminKey: ADMIN_KEY });

  const table = await screen.findByRole("table");
  expect(within(table).getAllByRole("row")).toHaveLength(3);
  expect(within(table).getByRole("row", { name: /Storefront/ })).toHaveTextContent("storefront");
  expect(within(table).getByRole("row", { name: /Billing/ })).toHaveTextContent("billing");
});

it("explains how to start when there are no projects", async () => {
  server.use(http.get("*/projects", () => HttpResponse.json([])));
  renderDashboard("/", { adminKey: ADMIN_KEY });

  expect(await screen.findByText("No projects yet.")).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

it("shows a failed load and loads again on request", async () => {
  let attempts = 0;
  server.use(
    http.get("*/projects", () => {
      attempts += 1;
      return attempts === 1
        ? new HttpResponse(null, { status: 502, statusText: "Bad Gateway" })
        : HttpResponse.json([storefront]);
    }),
  );
  const { user } = renderDashboard("/", { adminKey: ADMIN_KEY });

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "The server answered 502 Bad Gateway.",
  );
  await user.click(screen.getByRole("button", { name: "Try again" }));

  expect(await screen.findByRole("table")).toHaveTextContent("Storefront");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
