import { describe, expect, it } from "vitest";

import {
  formatValue,
  parseValue,
  parseVariants,
  startingVariants,
  variantDrafts,
} from "./variants";

describe("parseValue", () => {
  it("reads each kind of value from its text", () => {
    expect(parseValue("boolean", "false")).toEqual({ ok: true, value: false });
    expect(parseValue("number", " 2.5 ")).toEqual({ ok: true, value: 2.5 });
    expect(parseValue("string", " kept as typed ")).toEqual({ ok: true, value: " kept as typed " });
    expect(parseValue("json", '{"limit": [1, 2]}')).toEqual({ ok: true, value: { limit: [1, 2] } });
  });

  it.each([
    ["boolean", "yes"],
    ["number", ""],
    ["number", "ten"],
    ["number", "Infinity"],
    ["json", "{limit: 1}"],
  ] as const)("refuses a %s of %j", (kind, text) => {
    expect(parseValue(kind, text).ok).toBe(false);
  });
});

describe("parseVariants", () => {
  it("returns the variants the API expects", () => {
    const parsed = parseVariants("number", [
      { key: "low", value: "10" },
      { key: "high", value: "100" },
    ]);

    expect(parsed).toEqual({
      ok: true,
      value: [
        { key: "low", value: 10 },
        { key: "high", value: 100 },
      ],
    });
  });

  it("reports each problem against the variant it belongs to", () => {
    const parsed = parseVariants("number", [
      { key: "same", value: "1" },
      { key: "same", value: "x" },
      { key: "", value: "3" },
      { key: "bad key", value: "4" },
    ]);

    expect(parsed).toEqual({
      ok: false,
      errors: [
        { key: "Another variant has this key." },
        { key: "Another variant has this key.", value: "Enter a number, such as 10 or 0.5." },
        { key: "Give the variant a key." },
        { key: expect.stringContaining("letters, digits") as unknown },
      ],
    });
  });

  it("needs at least one variant", () => {
    expect(parseVariants("string", []).ok).toBe(false);
  });
});

it("formats a variant's value back into the text it was typed as", () => {
  const variants = [
    { key: "on", value: true },
    { key: "config", value: { limit: 3 } },
  ];

  expect(variantDrafts("boolean", variants.slice(0, 1))).toEqual([{ key: "on", value: "true" }]);
  expect(formatValue("json", variants[1]?.value)).toBe('{\n  "limit": 3\n}');
  expect(parseVariants("boolean", startingVariants("boolean"))).toEqual({
    ok: true,
    value: [
      { key: "on", value: true },
      { key: "off", value: false },
    ],
  });
});
