import { screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { expect, it } from "vitest";

import { ADMIN_KEY, adminKey, sdkKey } from "../test/fixtures";
import { renderDashboard } from "../test/render";
import { server } from "../test/server";

it("lists every key with what it can read", async () => {
  server.use(
    http.get("*/api-keys", () =>
      HttpResponse.json([adminKey, { ...sdkKey, revoked_at: "2026-10-05T09:00:00Z" }]),
    ),
  );
  renderDashboard("/api-keys", { adminKey: ADMIN_KEY });

  const table = await screen.findByRole("table");
  expect(within(table).getByRole("row", { name: /release tooling/ })).toHaveTextContent(
    "Everything, as an admin key",
  );
  const revoked = within(table).getByRole("row", { name: /checkout-api/ });
  expect(revoked).toHaveTextContent("prod of storefront");
  expect(revoked).toHaveTextContent(/Revoked/);
  expect(within(revoked).queryByRole("button")).not.toBeInTheDocument();
});

it("revokes a key once asked twice", async () => {
  const revoked: string[] = [];
  server.use(
    http.get("*/api-keys", () => HttpResponse.json([adminKey, sdkKey])),
    http.post("*/api-keys/:keyId/revoke", ({ params }) => {
      revoked.push(String(params.keyId));
      return HttpResponse.json({ ...sdkKey, revoked_at: "2026-10-20T09:00:00Z" });
    }),
  );
  const { user } = renderDashboard("/api-keys", { adminKey: ADMIN_KEY });

  await user.click(await screen.findByRole("button", { name: "Revoke checkout-api" }));
  expect(revoked).toEqual([]);
  await user.click(screen.getByRole("button", { name: "Revoke checkout-api now" }));

  const row = await screen.findByRole("row", { name: /checkout-api/ });
  expect(await within(row).findByText(/^Revoked/)).toBeVisible();
  expect(revoked).toEqual([sdkKey.id]);
});

it("leaves a key alone when the revoke isn't confirmed", async () => {
  server.use(http.get("*/api-keys", () => HttpResponse.json([sdkKey])));
  const { user } = renderDashboard("/api-keys", { adminKey: ADMIN_KEY });

  await user.click(await screen.findByRole("button", { name: "Revoke checkout-api" }));
  await user.click(screen.getByRole("button", { name: "Keep it" }));

  expect(screen.getByRole("button", { name: "Revoke checkout-api" })).toBeVisible();
});
