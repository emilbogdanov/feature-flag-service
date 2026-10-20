import { screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import type { FlagResponse, TargetingSchema } from "../api/schema";
import { serveStorefront, versionMismatch } from "../test/api";
import { ADMIN_KEY, developmentTargeting, edited, newCheckout } from "../test/fixtures";
import { renderDashboard } from "../test/render";
import { server } from "../test/server";

const PAGE = "/projects/storefront/flags/new-checkout/environments/dev";
const TARGETING = "*/projects/storefront/flags/new-checkout/environments/dev/targeting";

function withTargeting(flag: FlagResponse, targeting: TargetingSchema): FlagResponse {
  return edited(flag, { environments: { ...flag.environments, dev: targeting } });
}

// Accepts every save, answering with the flag as it would be after it.
function acceptSaves() {
  const sent: { body: TargetingSchema; ifMatch: string | null }[] = [];
  server.use(
    http.put(TARGETING, async ({ request }) => {
      const body = (await request.json()) as TargetingSchema;
      sent.push({ body, ifMatch: request.headers.get("If-Match") });
      return HttpResponse.json(withTargeting(newCheckout, body));
    }),
  );
  return sent;
}

async function openEditor() {
  serveStorefront();
  const rendered = renderDashboard(PAGE, { adminKey: ADMIN_KEY });
  await screen.findByRole("heading", { level: 1, name: "New checkout in Development" });
  return rendered;
}

const save = () => screen.getByRole("button", { name: "Save targeting for Development" });

describe("editing targeting", () => {
  it("saves the environment's targeting against the version it was loaded at", async () => {
    const sent = acceptSaves();
    const { user } = await openEditor();

    await user.click(save());

    expect(await screen.findByText(/^Saved\./)).toBeVisible();
    expect(sent).toEqual([{ body: developmentTargeting, ifMatch: '"7"' }]);
  });

  it("adds a rule with its conditions and a rollout", async () => {
    const sent = acceptSaves();
    const { user } = await openEditor();

    await user.click(screen.getByRole("button", { name: "Add rule" }));
    const rule = within(screen.getByRole("group", { name: "Rule 2" }));
    await user.type(rule.getByLabelText("Attribute"), "seats");
    await user.selectOptions(rule.getByLabelText("Comparison"), "gte");
    await user.type(rule.getByLabelText("Number"), "10");
    await user.click(rule.getByRole("button", { name: "Add user list" }));
    await user.type(rule.getByLabelText("User keys, one per line"), "user-1{Enter}user-2");
    const serve = within(rule.getByRole("group", { name: "Serve" }));
    await user.click(serve.getByRole("radio", { name: "A percentage of users each" }));
    await user.clear(serve.getByLabelText("on"));
    await user.type(serve.getByLabelText("on"), "33.333");
    await user.clear(serve.getByLabelText("off"));
    await user.type(serve.getByLabelText("off"), "66.667");
    await user.click(save());

    await screen.findByText(/^Saved\./);
    expect(sent[0]?.body.rules?.[1]).toEqual({
      id: "rule-2",
      conditions: [
        { type: "attribute", attribute: "seats", operator: "gte", values: [10], negate: false },
        { type: "user_list", user_keys: ["user-1", "user-2"] },
      ],
      serve: {
        rollout: [
          { variant: "on", weight: 33_333 },
          { variant: "off", weight: 66_667 },
        ],
      },
    });
  });

  it("moves a rule up so it is tried first", async () => {
    const sent = acceptSaves();
    const { user } = await openEditor();

    await user.click(screen.getByRole("button", { name: "Add rule" }));
    const added = within(screen.getByRole("group", { name: "Rule 2" }));
    await user.type(added.getByLabelText("Attribute"), "country");
    await user.type(added.getByLabelText("Values, one per line"), "DE");
    await user.click(added.getByRole("button", { name: "Move up" }));
    await user.click(save());

    await screen.findByText(/^Saved\./);
    expect(sent[0]?.body.rules?.map((rule) => rule.id)).toEqual(["rule-2", "staff"]);
  });

  it("points at what is wrong without sending anything", async () => {
    const sent = acceptSaves();
    const { user } = await openEditor();

    const everyoneElse = within(screen.getByRole("group", { name: "Everyone else" }));
    await user.clear(everyoneElse.getByLabelText("off"));
    await user.type(everyoneElse.getByLabelText("off"), "70");
    await user.click(save());

    expect(everyoneElse.getByText("The shares add up to 95%, not 100%.")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("Some fields need fixing");
    expect(sent).toEqual([]);
  });

  it("shows why the API refused the targeting", async () => {
    serveStorefront();
    server.use(
      http.put(TARGETING, () =>
        HttpResponse.json(
          { detail: "operator ends_with compares text, got (3,)", code: "invalid_targeting" },
          { status: 422 },
        ),
      ),
    );
    const { user } = renderDashboard(PAGE, { adminKey: ADMIN_KEY });

    await user.click(await screen.findByRole("button", { name: "Save targeting for Development" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Operator ends_with compares text, got (3,).",
    );
  });
});

describe("someone else changing the flag meanwhile", () => {
  it("keeps the edit, says why it can't be saved, and loads theirs on request", async () => {
    let current = newCheckout;
    serveStorefront();
    server.use(
      http.get("*/projects/storefront/flags/new-checkout", () => HttpResponse.json(current)),
      http.put(TARGETING, () => {
        current = withTargeting(newCheckout, {
          ...developmentTargeting,
          off_variant: "on",
        });
        return HttpResponse.json(versionMismatch, { status: 412 });
      }),
    );
    const { user } = renderDashboard(PAGE, { adminKey: ADMIN_KEY });

    await user.click(await screen.findByLabelText("On in Development"));
    await user.click(save());

    expect(await screen.findByText(/^The flag changed after you started editing/)).toBeVisible();
    expect(screen.getByLabelText("On in Development")).not.toBeChecked();
    await user.click(
      screen.getByRole("button", { name: "Discard my changes and load the latest" }),
    );

    expect(screen.getByLabelText("On in Development")).toBeChecked();
    expect(screen.getByLabelText("Served while off")).toHaveValue("on");
    expect(screen.queryByText(/^The flag changed/)).not.toBeInTheDocument();
  });
});

it("says so when the project has no such environment", async () => {
  serveStorefront();
  renderDashboard("/projects/storefront/flags/new-checkout/environments/qa", {
    adminKey: ADMIN_KEY,
  });

  expect(await screen.findByRole("heading", { name: "No such environment" })).toBeVisible();
});
