import { screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import type { CreateFlag, FlagResponse } from "../api/schema";
import { serveStorefront } from "../test/api";
import { ADMIN_KEY, newCheckout } from "../test/fixtures";
import { renderDashboard } from "../test/render";
import { server } from "../test/server";

// Answers a create with the flag it describes, and keeps what was sent.
function acceptCreate() {
  const sent: CreateFlag[] = [];
  server.use(
    http.post("*/projects/storefront/flags", async ({ request }) => {
      const body = (await request.json()) as CreateFlag;
      sent.push(body);
      const created: FlagResponse = {
        ...newCheckout,
        key: body.key,
        name: body.name,
        kind: body.kind,
        variants: body.variants.map((variant) => ({ key: variant.key, value: variant.value })),
      };
      server.use(
        http.get(`*/projects/storefront/flags/${body.key}`, () => HttpResponse.json(created)),
      );
      return HttpResponse.json(created, { status: 201 });
    }),
  );
  return sent;
}

describe("creating a flag", () => {
  it("creates a boolean flag with a key taken from its name", async () => {
    serveStorefront();
    const sent = acceptCreate();
    const { user, router } = renderDashboard("/projects/storefront/flags/new", {
      adminKey: ADMIN_KEY,
    });

    await user.type(await screen.findByLabelText("Name"), "Dark mode");
    expect(screen.getByLabelText("Key")).toHaveValue("dark-mode");
    await user.type(screen.getByLabelText("Description"), "Night colours for the storefront.");
    await user.click(screen.getByRole("button", { name: "Create flag" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Dark mode" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/projects/storefront/flags/dark-mode");
    expect(sent).toEqual([
      {
        key: "dark-mode",
        name: "Dark mode",
        description: "Night colours for the storefront.",
        kind: "boolean",
        variants: [
          { key: "on", value: true },
          { key: "off", value: false },
        ],
        off_variant: "off",
        on_variant: "on",
      },
    ]);
  });

  it("creates a number flag from the variants typed in", async () => {
    serveStorefront();
    const sent = acceptCreate();
    const { user } = renderDashboard("/projects/storefront/flags/new", { adminKey: ADMIN_KEY });

    await user.type(await screen.findByLabelText("Name"), "Search page size");
    await user.click(screen.getByRole("radio", { name: "Number" }));
    await user.type(screen.getByLabelText("Key of variant 1"), "small");
    await user.type(screen.getByLabelText("Value of variant 1"), "10");
    await user.type(screen.getByLabelText("Key of variant 2"), "large");
    await user.type(screen.getByLabelText("Value of variant 2"), "50");
    await user.selectOptions(screen.getByLabelText("Served when off"), "small");
    await user.selectOptions(screen.getByLabelText("Served when turned on"), "large");
    await user.click(screen.getByRole("button", { name: "Create flag" }));

    await screen.findByRole("heading", { level: 1, name: "Search page size" });
    expect(sent[0]).toMatchObject({
      key: "search-page-size",
      kind: "number",
      variants: [
        { key: "small", value: 10 },
        { key: "large", value: 50 },
      ],
      off_variant: "small",
      on_variant: "large",
    });
  });

  it("points at what is missing before sending anything", async () => {
    serveStorefront();
    const { user } = renderDashboard("/projects/storefront/flags/new", { adminKey: ADMIN_KEY });

    await user.click(await screen.findByRole("radio", { name: "Number" }));
    await user.type(screen.getByLabelText("Value of variant 1"), "lots");
    await user.click(screen.getByRole("button", { name: "Create flag" }));

    expect(screen.getByLabelText("Name")).toHaveAccessibleDescription("Give the flag a name.");
    expect(screen.getByLabelText("Value of variant 1")).toHaveAccessibleDescription(
      "Enter a number, such as 10 or 0.5.",
    );
    expect(screen.getByLabelText("Served when off")).toHaveAccessibleDescription(
      "Choose the variant to serve when off.",
    );
  });

  it("says when another flag already has the key", async () => {
    serveStorefront();
    server.use(
      http.post("*/projects/storefront/flags", () =>
        HttpResponse.json(
          { detail: "flag 'new-checkout' already exists", code: "flag_key_taken" },
          { status: 409 },
        ),
      ),
    );
    const { user } = renderDashboard("/projects/storefront/flags/new", { adminKey: ADMIN_KEY });

    await user.type(await screen.findByLabelText("Name"), "New checkout");
    await user.click(screen.getByRole("button", { name: "Create flag" }));

    expect(await screen.findByText("Another flag in this project has this key.")).toBeVisible();
    await user.type(screen.getByLabelText("Key"), "-v2");
    expect(
      screen.queryByText("Another flag in this project has this key."),
    ).not.toBeInTheDocument();
  });
});
