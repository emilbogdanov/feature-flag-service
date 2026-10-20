import { describe, expect, it } from "vitest";

import { ApiError } from "./client";
import { describeError, isUnauthorized } from "./errors";

describe("describeError", () => {
  it("turns the API's phrase into a sentence", () => {
    const error = new ApiError(404, "project_not_found", "project 'shop' does not exist");

    expect(describeError(error)).toBe("Project 'shop' does not exist.");
  });

  it("explains an edit refused because the flag changed meanwhile", () => {
    const error = new ApiError(412, "version_mismatch", "flag 'x' is at version 4, not 3");

    expect(describeError(error)).toMatch(/^Someone changed this flag/);
  });

  it("explains a request that got no response", () => {
    expect(describeError(new TypeError("Failed to fetch"))).toBe(
      "The API can't be reached. Check that it's running, then try again.",
    );
  });

  it("has a sentence for anything that isn't an error", () => {
    expect(describeError("boom")).toBe("Something unexpected went wrong.");
  });
});

it("recognises a rejected key by its status", () => {
  expect(isUnauthorized(new ApiError(401, "invalid_api_key", "revoked"))).toBe(true);
  expect(isUnauthorized(new ApiError(403, "forbidden", "needs an admin key"))).toBe(false);
});
