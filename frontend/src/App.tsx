import type { QueryClient } from "@tanstack/react-query";
import type { DataRouter } from "react-router";
import { RouterProvider } from "react-router/dom";

import { AppProviders } from "./AppProviders";

interface AppProps {
  router: DataRouter;
  queryClient?: QueryClient;
}

export function App({ router, queryClient }: AppProps) {
  return (
    <AppProviders {...(queryClient && { queryClient })}>
      <RouterProvider router={router} />
    </AppProviders>
  );
}
