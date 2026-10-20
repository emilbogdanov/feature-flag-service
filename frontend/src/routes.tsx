import type { RouteObject } from "react-router";

import { Layout } from "./layout/Layout";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { RouteErrorPage } from "./pages/RouteErrorPage";
import { SignInPage } from "./pages/SignInPage";
import { RequireSession } from "./session/RequireSession";

export const routes: RouteObject[] = [
  {
    errorElement: <RouteErrorPage />,
    children: [
      { path: "/sign-in", element: <SignInPage /> },
      {
        path: "/",
        element: (
          <RequireSession>
            <Layout />
          </RequireSession>
        ),
        children: [
          { index: true, element: <ProjectsPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];
