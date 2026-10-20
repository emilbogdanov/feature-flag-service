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
