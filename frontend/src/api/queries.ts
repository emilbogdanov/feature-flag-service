import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

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

export function flagsQuery(client: ApiClient, projectKey: string) {
  return queryOptions({
    queryKey: ["projects", projectKey, "flags"],
    queryFn: () =>
      unwrap(
        client.GET("/projects/{project_key}/flags", {
          params: { path: { project_key: projectKey } },
        }),
      ),
  });
}

export function flagQuery(client: ApiClient, projectKey: string, flagKey: string) {
  return queryOptions({
    queryKey: ["projects", projectKey, "flags", flagKey],
    queryFn: () =>
      unwrap(
        client.GET("/projects/{project_key}/flags/{flag_key}", {
          params: { path: { project_key: projectKey, flag_key: flagKey } },
        }),
      ),
  });
}

export function apiKeysQuery(client: ApiClient) {
  return queryOptions({
    queryKey: ["api-keys"],
    queryFn: () => unwrap(client.GET("/api-keys")),
  });
}

const AUDIT_PAGE_SIZE = 50;

// Newest first, a page at a time; each page says where the next one starts.
export function auditQuery(client: ApiClient, projectKey: string | null) {
  return infiniteQueryOptions({
    queryKey: ["audit", projectKey],
    queryFn: ({ pageParam }) =>
      unwrap(
        client.GET("/audit", {
          params: {
            query: { project: projectKey, cursor: pageParam, limit: AUDIT_PAGE_SIZE },
          },
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor,
  });
}
