import type {
  AttributeConditionSchema,
  Operator,
  RuleSchema,
  TargetingSchema,
  UserListConditionSchema,
  VariantSchema,
} from "../api/schema";
import { KEY_RULE, isValidKey } from "./keys";
import { type Serve, WEIGHT_TOTAL, formatPercent, isRollout } from "./serve";
import type { Parsed } from "./variants";

// The targeting of one environment as it is being edited. Values stay as typed until the form is
// sent, and every list item carries a uid so React keeps its inputs when items move.

export interface TargetingDraft {
  enabled: boolean;
  offVariant: string;
  rules: RuleDraft[];
  fallthrough: ServeDraft;
}

export interface RuleDraft {
  uid: string;
  id: string;
  conditions: ConditionDraft[];
  serve: ServeDraft;
}

export type ValueKind = "text" | "number" | "boolean";

export type ConditionDraft =
  | {
      uid: string;
      type: "attribute";
      attribute: string;
      operator: Operator;
      negate: boolean;
      valueKind: ValueKind;
      // One value per line.
      values: string;
    }
  | { uid: string; type: "user_list"; userKeys: string };

// Both ways of serving are kept while editing, so switching between them loses nothing.
export interface ServeDraft {
  mode: "fixed" | "rollout";
  variant: string;
  // In the order the rollout lists them: users are bucketed along that order, so keeping it
  // means growing one share only moves users from the shares next to it.
  shares: { variant: string; percent: string }[];
}

// Errors by the path of the field they belong to, such as "rules.0.conditions.1.values".
export type TargetingErrors = Map<string, string>;

export const OPERATOR_LABELS: Record<Operator, string> = {
  in: "is one of",
  contains: "contains",
  starts_with: "starts with",
  ends_with: "ends with",
  lt: "is less than",
  lte: "is at most",
  gt: "is greater than",
  gte: "is at least",
};

const COMPARISONS = new Set<Operator>(["lt", "lte", "gt", "gte"]);
const TEXT_MATCHES = new Set<Operator>(["contains", "starts_with", "ends_with"]);

export function takesOneNumber(operator: Operator): boolean {
  return COMPARISONS.has(operator);
}

export function takesText(operator: Operator): boolean {
  return TEXT_MATCHES.has(operator);
}

let lastUid = 0;
export function newUid(): string {
  lastUid += 1;
  return `draft-${String(lastUid)}`;
}

export function targetingDraft(
  targeting: TargetingSchema,
  variants: VariantSchema[],
): TargetingDraft {
  return {
    enabled: targeting.enabled,
    offVariant: targeting.off_variant,
    rules: (targeting.rules ?? []).map((rule) => ({
      uid: newUid(),
      id: rule.id,
      conditions: rule.conditions.map(conditionDraft),
      serve: serveDraft(rule.serve, variants),
    })),
    fallthrough: serveDraft(targeting.fallthrough, variants),
  };
}

export function newRule(rules: RuleDraft[], variants: VariantSchema[]): RuleDraft {
  const taken = new Set(rules.map((rule) => rule.id));
  let number = rules.length + 1;
  while (taken.has(`rule-${String(number)}`)) {
    number += 1;
  }
  return {
    uid: newUid(),
    id: `rule-${String(number)}`,
    conditions: [newCondition()],
    serve: serveDraft({ variant: variants[0]?.key ?? "" }, variants),
  };
}

export function newCondition(): ConditionDraft {
  return {
    uid: newUid(),
    type: "attribute",
    attribute: "",
    operator: "in",
    negate: false,
    valueKind: "text",
    values: "",
  };
}

export function newUserList(): ConditionDraft {
  return { uid: newUid(), type: "user_list", userKeys: "" };
}

function conditionDraft(
  condition: AttributeConditionSchema | UserListConditionSchema,
): ConditionDraft {
  if (condition.type === "user_list") {
    return { uid: newUid(), type: "user_list", userKeys: condition.user_keys.join("\n") };
  }
  return {
    uid: newUid(),
    type: "attribute",
    attribute: condition.attribute,
    operator: condition.operator,
    negate: condition.negate,
    valueKind: valueKindOf(condition.values),
    values: condition.values.map(String).join("\n"),
  };
}

function valueKindOf(values: (string | number | boolean)[]): ValueKind {
  if (values.length > 0 && values.every((value) => typeof value === "boolean")) {
    return "boolean";
  }
  if (values.length > 0 && values.every((value) => typeof value === "number")) {
    return "number";
  }
  return "text";
}

function serveDraft(serve: Serve, variants: VariantSchema[]): ServeDraft {
  if (!isRollout(serve)) {
    // Switching to a rollout starts from everyone on the variant served now.
    return {
      mode: "fixed",
      variant: serve.variant,
      shares: variants.map((variant) => ({
        variant: variant.key,
        percent: variant.key === serve.variant ? "100" : "0",
      })),
    };
  }
  const unlisted = variants
    .filter((variant) => !serve.rollout.some((share) => share.variant === variant.key))
    .map((variant) => ({ variant: variant.key, weight: 0 }));
  return {
    mode: "rollout",
    variant: serve.rollout[0]?.variant ?? "",
    shares: [...serve.rollout, ...unlisted].map((share) => ({
      variant: share.variant,
      percent: formatPercent(share.weight).replace("%", ""),
    })),
  };
}

export function parseTargeting(
  draft: TargetingDraft,
  variants: VariantSchema[],
): Parsed<TargetingSchema, TargetingErrors> {
  const errors: TargetingErrors = new Map();
  const known = new Set(variants.map((variant) => variant.key));

  if (!known.has(draft.offVariant)) {
    errors.set("offVariant", "Choose the variant to serve when off.");
  }
  const ruleIds = draft.rules.map((rule) => rule.id);
  const rules = draft.rules.map((rule, index): RuleSchema => {
    const path = `rules.${String(index)}`;
    if (!isValidKey(rule.id)) {
      errors.set(`${path}.id`, rule.id === "" ? "Give the rule an id." : KEY_RULE);
    } else if (ruleIds.indexOf(rule.id) !== index) {
      errors.set(`${path}.id`, "Another rule has this id.");
    }
    if (rule.conditions.length === 0) {
      errors.set(`${path}.conditions`, "A rule needs at least one condition.");
    }
    return {
      id: rule.id,
      conditions: rule.conditions.map((condition, at) =>
        parseCondition(condition, `${path}.conditions.${String(at)}`, errors),
      ),
      serve: parseServe(rule.serve, known, `${path}.serve`, errors),
    };
  });
  const fallthrough = parseServe(draft.fallthrough, known, "fallthrough", errors);

  return errors.size > 0
    ? { ok: false, errors }
    : {
        ok: true,
        value: { enabled: draft.enabled, off_variant: draft.offVariant, rules, fallthrough },
      };
}

function parseCondition(
  condition: ConditionDraft,
  path: string,
  errors: TargetingErrors,
): AttributeConditionSchema | UserListConditionSchema {
  if (condition.type === "user_list") {
    const userKeys = lines(condition.userKeys);
    if (userKeys.length === 0) {
      errors.set(`${path}.userKeys`, "List at least one user key, one per line.");
    }
    return { type: "user_list", user_keys: userKeys };
  }

  if (condition.attribute.trim() === "") {
    errors.set(`${path}.attribute`, "Name the attribute to compare.");
  }
  const values = parseConditionValues(condition, `${path}.values`, errors);
  return {
    type: "attribute",
    attribute: condition.attribute.trim(),
    operator: condition.operator,
    values,
    negate: condition.negate,
  };
}

function parseConditionValues(
  condition: Extract<ConditionDraft, { type: "attribute" }>,
  path: string,
  errors: TargetingErrors,
): (string | number | boolean)[] {
  const typed = lines(condition.values);
  if (takesOneNumber(condition.operator)) {
    const number = Number(typed[0]);
    if (typed.length !== 1 || !Number.isFinite(number)) {
      errors.set(path, "Enter one number to compare with.");
      return [];
    }
    return [number];
  }
  if (typed.length === 0) {
    errors.set(path, "Enter at least one value, one per line.");
    return [];
  }
  if (takesText(condition.operator) || condition.valueKind === "text") {
    return typed;
  }
  if (condition.valueKind === "number") {
    const numbers = typed.map(Number);
    if (!numbers.every(Number.isFinite)) {
      errors.set(path, "Every value has to be a number.");
    }
    return numbers;
  }
  if (!typed.every((value) => value === "true" || value === "false")) {
    errors.set(path, "Every value has to be true or false.");
  }
  return typed.map((value) => value === "true");
}

function parseServe(
  serve: ServeDraft,
  known: Set<string>,
  path: string,
  errors: TargetingErrors,
): Serve {
  if (serve.mode === "fixed") {
    if (!known.has(serve.variant)) {
      errors.set(path, "Choose a variant to serve.");
    }
    return { variant: serve.variant };
  }

  const weights = serve.shares.map((share) => ({
    variant: share.variant,
    weight: weightOf(share.percent),
  }));
  if (weights.some((share) => share.weight === null)) {
    errors.set(path, "Give every share a percentage from 0 to 100, to at most three decimals.");
    return { rollout: [] };
  }
  const rollout = weights
    .filter((share): share is { variant: string; weight: number } => (share.weight ?? 0) > 0)
    .filter((share) => known.has(share.variant));
  const total = rollout.reduce((sum, share) => sum + share.weight, 0);
  if (total !== WEIGHT_TOTAL) {
    errors.set(path, `The shares add up to ${formatPercent(total)}, not 100%.`);
  }
  return { rollout };
}

// A percentage such as "12.5" as a weight out of 100,000, or null when it isn't one.
function weightOf(percent: string): number | null {
  const text = percent.trim() === "" ? "0" : percent.trim();
  if (!/^\d{1,3}(\.\d{1,3})?$/.test(text)) {
    return null;
  }
  const weight = Math.round(Number(text) * (WEIGHT_TOTAL / 100));
  return weight <= WEIGHT_TOTAL ? weight : null;
}

function lines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
}
