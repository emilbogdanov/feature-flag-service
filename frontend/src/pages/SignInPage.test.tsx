import { screen } from "@testing-library/react";
import { HttpResponse, type JsonBodyType, http } from "msw";
import { describe, expect, it } from "vitest";

import { readStoredKey } from "../session/storage";
import { ADMIN_KEY, storefront } from "../test/fixtures";
import { renderDashboard } from "../test/render";
import { server } from "../test/server";

function answerProjects(status: number, body: JsonBodyType) {
  const keys: (string | null)[] = [];
  server.use(
    http.get("*/projects", ({ request }) => {
      keys.push(request.headers.get("Authorization"));
      return HttpResponse.json(body, { status });
    }),
  );
  return keys;
}

describe("signing in", () => {
  it("sends a signed-out visitor to the sign-in form", async () => {
    renderDashboard("/");

    expect(await screen.findByLabelText("Admin key")).toBeInTheDocument();
  });

  it("checks the key against the API, keeps it for the tab and shows the projects", async () => {
    const keys = answerProjects(200, [storefront]);
    const { user, router } = renderDashboard("/sign-in");

    await user.type(screen.getByLabelText("Admin key"), `  ${ADMIN_KEY}  `);
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(screen.getByRole("table")).toHaveTextContent("Storefront");
    expect(router.state.location.pathname).toBe("/");
    expect(readStoredKey()).toBe(ADMIN_KEY);
    // The list came with the check, so signing in costs one request.
    expect(keys).toEqual([`Bearer ${ADMIN_KEY}`]);
  });

  it("says when the API doesn't know the key", async () => {
    answerProjects(401, {
      detail: "API key is missing, unknown or revoked",
      code: "invalid_api_key",
    });
    const { user } = renderDashboard("/sign-in");

    await user.type(screen.getByLabelText("Admin key"), "fs_admin_wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The API doesn't accept this key");
    expect(screen.getByLabelText("Admin key")).toHaveAttribute("aria-invalid", "true");
    expect(readStoredKey()).toBeNull();
  });

  it("says when the key is an SDK key", async () => {
    answerProjects(403, { detail: "this endpoint needs an admin key", code: "forbidden" });
    const { user } = renderDashboard("/sign-in");

    await user.type(screen.getByLabelText("Admin key"), "fs_sdk_x");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("This is an SDK key");
  });

  it("does nothing with an empty key", async () => {
    const { user } = renderDashboard("/sign-in");

    await user.type(screen.getByLabelText("Admin key"), "   ");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    // No handler is installed, so any request would fail the test.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("signing out", () => {
  it("forgets the key", async () => {
    answerProjects(200, [storefront]);
    const { user } = renderDashboard("/", { adminKey: ADMIN_KEY });

    await user.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(await screen.findByLabelText("Admin key")).toBeInTheDocument();
    expect(readStoredKey()).toBeNull();
  });

  it("happens by itself when the API stops accepting the key", async () => {
    answerProjects(401, {
      detail: "API key is missing, unknown or revoked",
      code: "invalid_api_key",
    });
    renderDashboard("/", { adminKey: ADMIN_KEY });

    expect(await screen.findByLabelText("Admin key")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "The API stopped accepting your admin key.",
    );
    expect(readStoredKey()).toBeNull();
  });
});
