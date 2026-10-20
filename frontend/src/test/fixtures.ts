import type {
  ApiKeyResponse,
  AuditEntryResponse,
  EnvironmentResponse,
  FlagResponse,
  ProjectResponse,
  TargetingSchema,
} from "../api/schema";

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

const offEverywhere = {
  enabled: false,
  off_variant: "off",
  rules: [],
  fallthrough: { variant: "on" },
};

export const developmentTargeting: TargetingSchema = {
  enabled: true,
  off_variant: "off",
  rules: [
    {
      id: "staff",
      conditions: [
        {
          type: "attribute",
          attribute: "email",
          operator: "ends_with",
          values: ["@shop.test"],
          negate: false,
        },
      ],
      serve: { variant: "on" },
    },
  ],
  fallthrough: {
    rollout: [
      { variant: "on", weight: 25_000 },
      { variant: "off", weight: 75_000 },
    ],
  },
};

export const newCheckout: FlagResponse = {
  key: "new-checkout",
  name: "New checkout",
  description: "The one-page checkout.",
  kind: "boolean",
  variants: [
    { key: "on", value: true },
    { key: "off", value: false },
  ],
  version: 7,
  environments: {
    dev: developmentTargeting,
    staging: offEverywhere,
    prod: offEverywhere,
  },
  created_at: "2026-10-03T09:00:00Z",
  updated_at: "2026-10-04T09:00:00Z",
  archived_at: null,
};

// The flag as the API answers after it was switched or edited: one version on.
export function edited(flag: FlagResponse, change: Partial<FlagResponse>): FlagResponse {
  return { ...flag, ...change, version: flag.version + 1 };
}

export function switched(flag: FlagResponse, environmentKey: string, enabled: boolean) {
  const targeting = flag.environments[environmentKey];
  if (targeting === undefined) {
    throw new Error(`${flag.key} has no targeting for ${environmentKey}`);
  }
  return edited(flag, {
    environments: { ...flag.environments, [environmentKey]: { ...targeting, enabled } },
  });
}

export const adminKey: ApiKeyResponse = {
  id: "5c6f0d8e-1a2b-4c3d-8e9f-000000000001",
  kind: "admin",
  name: "release tooling",
  project: null,
  environment: null,
  created_at: "2026-10-01T09:00:00Z",
  revoked_at: null,
};

export const sdkKey: ApiKeyResponse = {
  id: "5c6f0d8e-1a2b-4c3d-8e9f-000000000002",
  kind: "sdk",
  name: "checkout-api",
  project: "storefront",
  environment: "prod",
  created_at: "2026-10-02T09:00:00Z",
  revoked_at: null,
};

export function auditEntry(change: Partial<AuditEntryResponse>): AuditEntryResponse {
  return {
    id: crypto.randomUUID(),
    action: "flag.enabled",
    actor: { api_key_id: adminKey.id, name: adminKey.name },
    at: "2026-10-20T09:00:00Z",
    project: "storefront",
    environment: "prod",
    subject: "new-checkout",
    changes: {},
    ...change,
  };
}
