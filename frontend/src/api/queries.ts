import { queryOptions } from "@tanstack/react-query";

import { type ApiClient, unwrap } from "./client";

// The client is left out of the query keys: it changes only with the admin key, and signing out
// clears the cache.

export function projectsQuery(client: ApiClient) {
  return queryOptions({
    queryKey: ["projects"],
    queryFn: () => unwrap(client.GET("/projects")),
  });
}

export function projectQuery(client: ApiClient, projectKey: string) {
  return queryOptions({
    queryKey: ["projects", projectKey],
    queryFn: () =>
      unwrap(
        client.GET("/projects/{project_key}", { params: { path: { project_key: projectKey } } }),
      ),
  });
}

export function environmentsQuery(client: ApiClient, projectKey: string) {
  return queryOptions({
    queryKey: ["projects", projectKey, "environments"],
    queryFn: () =>
      unwrap(
        client.GET("/projects/{project_key}/environments", {
          params: { path: { project_key: projectKey } },
        }),
      ),
  });
}
