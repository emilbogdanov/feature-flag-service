import { describe, expect, it } from "vitest";

import type { TargetingSchema } from "../api/schema";
import { type TargetingDraft, newRule, parseTargeting, targetingDraft } from "./targeting";

const variants = [
  { key: "on", value: true },
  { key: "off", value: false },
];

const targeting: TargetingSchema = {
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
        { type: "attribute", attribute: "seats", operator: "gte", values: [10], negate: true },
        { type: "user_list", user_keys: ["user-1", "user-2"] },
      ],
      serve: { variant: "on" },
    },
  ],
  fallthrough: {
    rollout: [
      { variant: "on", weight: 12_500 },
      { variant: "off", weight: 87_500 },
    ],
  },
};

function edit(change: (draft: TargetingDraft) => void): TargetingDraft {
  const draft = targetingDraft(targeting, variants);
  change(draft);
  return draft;
}

function attribute(draft: TargetingDraft, rule: number, condition: number) {
  const found = draft.rules[rule]?.conditions[condition];
  if (found?.type !== "attribute") {
    throw new Error("expected an attribute condition");
  }
  return found;
}

describe("a targeting draft", () => {
  it("turns back into the targeting it was made from", () => {
    expect(parseTargeting(targetingDraft(targeting, variants), variants)).toEqual({
      ok: true,
      value: targeting,
    });
  });

  it("shows values as lines and rollout weights as percentages", () => {
    const draft = targetingDraft(targeting, variants);

    expect(draft.rules[0]?.conditions[2]).toMatchObject({ userKeys: "user-1\nuser-2" });
    expect(attribute(draft, 0, 1)).toMatchObject({ valueKind: "number", values: "10" });
    expect(draft.fallthrough.shares).toEqual([
      { variant: "on", percent: "12.5" },
      { variant: "off", percent: "87.5" },
    ]);
  });

  it("starts a rollout from everyone on the variant served so far", () => {
    const draft = targetingDraft({ ...targeting, fallthrough: { variant: "off" } }, variants);

    expect(draft.fallthrough.shares).toEqual([
      { variant: "on", percent: "0" },
      { variant: "off", percent: "100" },
    ]);
  });

  it("keeps a rollout's order and leaves out empty shares", () => {
    const draft = edit((changed) => {
      changed.fallthrough.shares = [
        { variant: "off", percent: "100" },
        { variant: "on", percent: "" },
      ];
    });

    const parsed = parseTargeting(draft, variants);

    expect(parsed.ok && parsed.value.fallthrough).toEqual({
      rollout: [{ variant: "off", weight: 100_000 }],
    });
  });

  it("reads values by the kind chosen for them", () => {
    const draft = edit((changed) => {
      Object.assign(attribute(changed, 0, 0), {
        operator: "in",
        valueKind: "boolean",
        values: "true\n\n false ",
      });
    });

    const parsed = parseTargeting(draft, variants);

    expect(parsed.ok && parsed.value.rules?.[0]?.conditions[0]).toMatchObject({
      values: [true, false],
    });
  });
});

describe("checking a targeting draft", () => {
  function errorsOf(draft: TargetingDraft) {
    const parsed = parseTargeting(draft, variants);
    return parsed.ok ? new Map() : parsed.errors;
  }

  it("finds shares that don't add up", () => {
    const draft = edit((changed) => {
      changed.fallthrough.shares = [
        { variant: "on", percent: "50" },
        { variant: "off", percent: "45.5" },
      ];
    });

    expect(errorsOf(draft).get("fallthrough")).toBe("The shares add up to 95.5%, not 100%.");
  });

  it.each(["-5", "101", "12.3456", "ten"])("refuses a share of %j", (percent) => {
    const draft = edit((changed) => {
      changed.fallthrough.shares[0] = { variant: "on", percent };
    });

    expect(errorsOf(draft).get("fallthrough")).toMatch(/^Give every share a percentage/);
  });

  it("puts each problem on the field it belongs to", () => {
    const draft = edit((changed) => {
      changed.offVariant = "gone";
      changed.rules.push({ ...newRule(changed.rules, variants), id: "staff", conditions: [] });
      Object.assign(attribute(changed, 0, 0), { attribute: " " });
      Object.assign(attribute(changed, 0, 1), { values: "10\n20" });
      changed.rules[0]?.conditions.push({ uid: "x", type: "user_list", userKeys: "\n" });
    });

    expect(Object.fromEntries(errorsOf(draft))).toEqual({
      offVariant: "Choose the variant to serve when off.",
      "rules.0.conditions.0.attribute": "Name the attribute to compare.",
      "rules.0.conditions.1.values": "Enter one number to compare with.",
      "rules.0.conditions.3.userKeys": "List at least one user key, one per line.",
      "rules.1.id": "Another rule has this id.",
      "rules.1.conditions": "A rule needs at least one condition.",
    });
  });

  it.each([
    ["number", "10\nlots", "Every value has to be a number."],
    ["boolean", "yes", "Every value has to be true or false."],
    ["text", "", "Enter at least one value, one per line."],
  ] as const)("checks %s values", (valueKind, values, error) => {
    const draft = edit((changed) => {
      Object.assign(attribute(changed, 0, 0), { operator: "in", valueKind, values });
    });

    expect(errorsOf(draft).get("rules.0.conditions.0.values")).toBe(error);
  });
});

it("gives a new rule an id no other rule has", () => {
  const rules = targetingDraft(targeting, variants).rules;
  rules.push({ ...newRule(rules, variants), id: "rule-2" });

  const rule = newRule(rules, variants);

  expect(rule.id).toBe("rule-3");
  expect(rule.conditions).toHaveLength(1);
  expect(rule.serve).toMatchObject({ mode: "fixed", variant: "on" });
  expect(rule.conditions[0]?.type).toBe("attribute");
});
