import type { FlagKind, VariantSchema } from "../api/schema";
import { KEY_RULE, isValidKey } from "./keys";

// A variant as it is being typed: the value is the text in its input, parsed by the flag's kind
// only when the form is sent.
export interface VariantDraft {
  key: string;
  value: string;
}

export interface VariantErrors {
  key?: string;
  value?: string;
}

export type Parsed<T, E> = { ok: true; value: T } | { ok: false; errors: E };

export const KIND_LABELS: Record<FlagKind, string> = {
  boolean: "Boolean",
  string: "Text",
  number: "Number",
  json: "JSON",
};

export function startingVariants(kind: FlagKind): VariantDraft[] {
  return kind === "boolean"
    ? [
        { key: "on", value: "true" },
        { key: "off", value: "false" },
      ]
    : [
        { key: "", value: "" },
        { key: "", value: "" },
      ];
}

export function variantDrafts(kind: FlagKind, variants: VariantSchema[]): VariantDraft[] {
  return variants.map((variant) => ({ key: variant.key, value: formatValue(kind, variant.value) }));
}

export function formatValue(kind: FlagKind, value: unknown): string {
  switch (kind) {
    case "string":
      return typeof value === "string" ? value : "";
    case "json":
      return JSON.stringify(value, null, 2);
    case "boolean":
    case "number":
      return String(value);
  }
}

export function parseVariants(
  kind: FlagKind,
  drafts: VariantDraft[],
): Parsed<VariantSchema[], VariantErrors[]> {
  const counts = new Map<string, number>();
  for (const draft of drafts) {
    counts.set(draft.key, (counts.get(draft.key) ?? 0) + 1);
  }

  const variants: VariantSchema[] = [];
  const errors = drafts.map((draft) => {
    const found: VariantErrors = {};
    if (!isValidKey(draft.key)) {
      found.key = draft.key === "" ? "Give the variant a key." : KEY_RULE;
    } else if ((counts.get(draft.key) ?? 0) > 1) {
      found.key = "Another variant has this key.";
    }
    const value = parseValue(kind, draft.value);
    if (value.ok) {
      variants.push({ key: draft.key, value: value.value });
    } else {
      found.value = value.errors;
    }
    return found;
  });

  if (drafts.length === 0) {
    return { ok: false, errors: [] };
  }
  return errors.some((found) => found.key !== undefined || found.value !== undefined)
    ? { ok: false, errors }
    : { ok: true, value: variants };
}

export function parseValue(kind: FlagKind, text: string): Parsed<unknown, string> {
  switch (kind) {
    case "string":
      return { ok: true, value: text };
    case "boolean":
      return text === "true" || text === "false"
        ? { ok: true, value: text === "true" }
        : { ok: false, errors: "Choose true or false." };
    case "number": {
      const number = Number(text.trim());
      return text.trim() !== "" && Number.isFinite(number)
        ? { ok: true, value: number }
        : { ok: false, errors: "Enter a number, such as 10 or 0.5." };
    }
    case "json":
      try {
        return { ok: true, value: JSON.parse(text) as unknown };
      } catch {
        return { ok: false, errors: 'Enter valid JSON, such as {"limit": 10}.' };
      }
  }
}
