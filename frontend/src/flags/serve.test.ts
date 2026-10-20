import { describe, expect, it } from "vitest";

import { describeServe, formatPercent } from "./serve";

describe("formatPercent", () => {
  it.each([
    [100_000, "100%"],
    [20_000, "20%"],
    [12_345, "12.345%"],
    [1, "0.001%"],
  ])("shows a weight of %i as %s", (weight, percent) => {
    expect(formatPercent(weight)).toBe(percent);
  });
});

describe("describeServe", () => {
  it("names a fixed variant", () => {
    expect(describeServe({ variant: "on" })).toBe("on");
  });

  it("lists a rollout's shares in order", () => {
    const serve = {
      rollout: [
        { variant: "on", weight: 25_000 },
        { variant: "off", weight: 75_000 },
      ],
    };

    expect(describeServe(serve)).toBe("on 25%, off 75%");
  });
});
