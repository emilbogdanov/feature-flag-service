import type { RouteObject } from "react-router";

import { Layout } from "./layout/Layout";
import { ApiKeysPage } from "./pages/ApiKeysPage";
import { FlagPage } from "./pages/FlagPage";
import { NewFlagPage } from "./pages/NewFlagPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ProjectPage } from "./pages/ProjectPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { RouteErrorPage } from "./pages/RouteErrorPage";
import { SignInPage } from "./pages/SignInPage";
import { TargetingPage } from "./pages/TargetingPage";
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
          { path: "projects/:projectKey", element: <ProjectPage /> },
          { path: "projects/:projectKey/flags/new", element: <NewFlagPage /> },
          { path: "projects/:projectKey/flags/:flagKey", element: <FlagPage /> },
          {
            path: "projects/:projectKey/flags/:flagKey/environments/:environmentKey",
            element: <TargetingPage />,
          },
          { path: "api-keys", element: <ApiKeysPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];
