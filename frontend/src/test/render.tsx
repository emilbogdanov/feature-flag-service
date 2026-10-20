import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter } from "react-router";

import { createQueryClient } from "../api/query-client";
import { App } from "../App";
import { routes } from "../routes";
import { storeKey } from "../session/storage";

interface RenderOptions {
  // Signed in with this key, as after a reload of a tab that had signed in.
  adminKey?: string;
}

export function renderDashboard(path: string, { adminKey }: RenderOptions = {}) {
  if (adminKey !== undefined) {
    storeKey(adminKey);
  }
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const queryClient = createQueryClient();
  const defaults = queryClient.getDefaultOptions();
  // Failures show at once instead of after the retries the real client makes.
  queryClient.setDefaultOptions({ ...defaults, queries: { ...defaults.queries, retry: false } });
  const user = userEvent.setup();
  render(<App router={router} queryClient={queryClient} />);
  return { router, user };
}
