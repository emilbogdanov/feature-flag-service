import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { App } from "./App";

it("renders the dashboard's frame", () => {
  render(<App />);

  expect(screen.getByRole("banner")).toHaveTextContent("Flagstaff");
  expect(screen.getByRole("main")).toBeInTheDocument();
});
