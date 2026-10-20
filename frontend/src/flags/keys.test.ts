import { describe, expect, it } from "vitest";

import { isValidKey, keyFromName } from "./keys";

describe("isValidKey", () => {
  it.each(["new-checkout", "v2", "checkout.theme", "A_b-9"])("accepts %s", (key) => {
    expect(isValidKey(key)).toBe(true);
  });

  it.each(["", "-leading", "with space", "flag:user", "é", "x".repeat(129)])(
    "rejects %j",
    (key) => {
      expect(isValidKey(key)).toBe(false);
    },
  );
});

describe("keyFromName", () => {
  it.each([
    ["New checkout", "new-checkout"],
    ["  Dark mode (beta)!  ", "dark-mode-beta"],
    ["Crème brûlée", "creme-brulee"],
    ["--Search v2.1", "search-v2.1"],
    ["日本", ""],
  ])("turns %j into %j", (name, key) => {
    expect(keyFromName(name)).toBe(key);
  });

  it("stays within the key length", () => {
    expect(keyFromName("a ".repeat(200))).toHaveLength(127);
    expect(isValidKey(keyFromName("a ".repeat(200)))).toBe(true);
  });
});
