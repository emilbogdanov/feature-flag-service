import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "./server";

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
});

afterEach(() => {
  // Testing Library unmounts after each test by itself only when the test functions are globals.
  cleanup();
  server.resetHandlers();
  sessionStorage.clear();
});

afterAll(() => {
  server.close();
});
