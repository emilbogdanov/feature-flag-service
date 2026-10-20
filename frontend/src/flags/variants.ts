import type { FlagKind } from "../api/schema";

export const KIND_LABELS: Record<FlagKind, string> = {
  boolean: "Boolean",
  string: "Text",
  number: "Number",
  json: "JSON",
};

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
