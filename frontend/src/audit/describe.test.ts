import { describe, expect, it } from "vitest";

import type { AuditEntryResponse } from "../api/schema";
import { describeAction } from "./describe";

const enabled: AuditEntryResponse = {
  id: "0b0c3d1e-0000-4000-8000-000000000001",
  action: "flag.enabled",
  actor: { api_key_id: null, name: "release-bot" },
  at: "2026-10-20T09:00:00Z",
  project: "storefront",
  environment: "prod",
  subject: "new-checkout",
  changes: {},
};

describe("describeAction", () => {
  it("names the flag and where it was changed", () => {
    expect(describeAction(enabled)).toEqual({
      verb: "turned on",
      subject: "new-checkout",
      place: { preposition: "in", path: "storefront/prod" },
    });
  });

  it("leaves out the project a log is already showing", () => {
    expect(describeAction(enabled, "storefront").place).toEqual({
      preposition: "in",
      path: "prod",
    });
  });

  it("says what an SDK key is for", () => {
    const issued = { ...enabled, action: "api_key.issued" as const, subject: "checkout-api" };

    expect(describeAction(issued).place).toEqual({ preposition: "for", path: "storefront/prod" });
  });

  it("puts a new environment in its project, not in itself", () => {
    const added = { ...enabled, action: "environment.created" as const, subject: "qa" };

    expect(describeAction(added)).toEqual({
      verb: "added the environment",
      subject: "qa",
      place: { preposition: "in", path: "storefront" },
    });
    expect(describeAction(added, "storefront").place).toBeNull();
  });

  it("has no place for a new project", () => {
    const created = { ...enabled, action: "project.created" as const, environment: null };

    expect(describeAction(created).place).toBeNull();
  });
});
