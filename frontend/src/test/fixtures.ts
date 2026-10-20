import type { EnvironmentResponse, ProjectResponse } from "../api/schema";

export const ADMIN_KEY = "fs_admin_test";

export const storefront: ProjectResponse = {
  key: "storefront",
  name: "Storefront",
  created_at: "2026-10-01T09:00:00Z",
};

export const billing: ProjectResponse = {
  key: "billing",
  name: "Billing",
  created_at: "2026-10-02T09:00:00Z",
};

export const storefrontEnvironments: EnvironmentResponse[] = [
  { key: "dev", name: "Development", created_at: "2026-10-01T09:00:00Z", ruleset_version: 12 },
  { key: "staging", name: "Staging", created_at: "2026-10-01T09:00:00Z", ruleset_version: 4 },
  { key: "prod", name: "Production", created_at: "2026-10-01T09:00:00Z", ruleset_version: 3 },
];
