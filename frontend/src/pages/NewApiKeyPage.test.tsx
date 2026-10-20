import { screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import type { IssueApiKey } from "../api/schema";
import { ADMIN_KEY, sdkKey, storefront, storefrontEnvironments } from "../test/fixtures";
import { renderDashboard } from "../test/render";
import { server } from "../test/server";

const SECRET = "fs_sdk_0123456789abcdef";

function acceptIssue() {
  const sent: IssueApiKey[] = [];
  server.use(
    http.get("*/projects", () => HttpResponse.json([storefront])),
    http.get("*/projects/storefront/environments", () => HttpResponse.json(storefrontEnvironments)),
    http.get("*/api-keys", () => HttpResponse.json([sdkKey])),
    http.post("*/api-keys", async ({ request }) => {
      const body = (await request.json()) as IssueApiKey;
      sent.push(body);
      return HttpResponse.json({ ...sdkKey, ...body, secret: SECRET }, { status: 201 });
    }),
  );
  return sent;
}

describe("issuing a key", () => {
  it("issues an SDK key for one environment and shows its secret once", async () => {
    const sent = acceptIssue();
    const { user } = renderDashboard("/api-keys/new", { adminKey: ADMIN_KEY });

    await user.type(await screen.findByLabelText("Name"), "checkout-api");
    await user.selectOptions(screen.getByLabelText("Project"), "storefront");
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Environment" }),
      await screen.findByRole("option", { name: "prod" }),
    );
    await user.click(screen.getByRole("button", { name: "Issue key" }));

    expect(await screen.findByLabelText("Secret")).toHaveValue(SECRET);
    expect(sent).toEqual([
      { kind: "sdk", name: "checkout-api", project: "storefront", environment: "prod" },
    ]);
    await user.click(screen.getByRole("button", { name: "Copy secret" }));
    // user-event stands in a clipboard of its own for the test.
    expect(await navigator.clipboard.readText()).toBe(SECRET);
    expect(screen.getByText("Copied to the clipboard.")).toBeVisible();
  });

  it("issues an admin key without a project or environment", async () => {
    const sent = acceptIssue();
    const { user } = renderDashboard("/api-keys/new", { adminKey: ADMIN_KEY });

    await user.click(await screen.findByRole("radio", { name: /^Admin key/ }));
    await user.type(screen.getByLabelText("Name"), "Dana");
    await user.click(screen.getByRole("button", { name: "Issue key" }));

    await screen.findByLabelText("Secret");
    expect(sent).toEqual([{ kind: "admin", name: "Dana" }]);
    expect(screen.getByRole("link", { name: "Done" })).toHaveAttribute("href", "/api-keys");
  });

  it("asks for what an SDK key needs before issuing it", async () => {
    const sent = acceptIssue();
    const { user } = renderDashboard("/api-keys/new", { adminKey: ADMIN_KEY });

    await user.click(await screen.findByRole("button", { name: "Issue key" }));

    expect(screen.getByLabelText("Name")).toHaveAccessibleDescription(/Say who or what/);
    expect(screen.getByLabelText("Project")).toHaveAccessibleDescription(
      "Choose the project it reads.",
    );
    expect(sent).toEqual([]);
  });
});
