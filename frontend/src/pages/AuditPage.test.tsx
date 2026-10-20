import { screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { expect, it } from "vitest";

import { ADMIN_KEY, auditEntry, billing, storefront } from "../test/fixtures";
import { renderDashboard } from "../test/render";
import { server } from "../test/server";

const newest = auditEntry({ action: "flag.disabled", subject: "new-checkout" });
const older = auditEntry({
  action: "flag.created",
  environment: null,
  changes: { kind: "boolean" },
});

function serveLog() {
  const asked: URLSearchParams[] = [];
  server.use(
    http.get("*/projects", () => HttpResponse.json([storefront, billing])),
    http.get("*/audit", ({ request }) => {
      const query = new URL(request.url).searchParams;
      asked.push(query);
      return query.get("cursor") === "page-2"
        ? HttpResponse.json({ entries: [older], next_cursor: null })
        : HttpResponse.json({ entries: [newest], next_cursor: "page-2" });
    }),
  );
  return asked;
}

it("reads the log a page at a time, newest first", async () => {
  serveLog();
  const { user } = renderDashboard("/audit", { adminKey: ADMIN_KEY });

  const changes = await screen.findByRole("region", { name: "Changes" });
  expect(await within(changes).findByText(/turned off/)).toHaveTextContent(
    "release tooling turned off new-checkout in storefront/prod",
  );
  await user.click(screen.getByRole("button", { name: "Show older changes" }));

  const entries = await within(changes).findAllByRole("listitem");
  expect(entries).toHaveLength(2);
  expect(entries[1]).toHaveTextContent("created the flag new-checkout in storefront");
  expect(screen.queryByRole("button", { name: "Show older changes" })).not.toBeInTheDocument();
});

it("shows one project's changes when asked for them", async () => {
  const asked = serveLog();
  const { user, router } = renderDashboard("/audit", { adminKey: ADMIN_KEY });

  await screen.findByText(/turned off/);
  await user.selectOptions(screen.getByLabelText("Project"), "billing");

  expect(router.state.location.search).toBe("?project=billing");
  await screen.findByText(/turned off/);
  expect(asked.map((query) => query.get("project"))).toEqual([null, "billing"]);
});

it("opens filtered to a project from its address", async () => {
  serveLog();
  renderDashboard("/audit?project=storefront", { adminKey: ADMIN_KEY });

  expect(await screen.findByText(/turned off/)).toHaveTextContent(
    "release tooling turned off new-checkout in prod",
  );
  expect(screen.getByLabelText("Project")).toHaveValue("storefront");
});
