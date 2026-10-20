import { type QueryClient, useMutation, useQueryClient } from "@tanstack/react-query";

import { type ApiClient, unwrap } from "../api/client";
import { environmentsQuery, flagQuery, flagsQuery } from "../api/queries";
import type { CreateFlag, FlagResponse } from "../api/schema";
import { useApiClient } from "../session/session-context";

// Edits name the version they were made against, so one made on a stale page is refused with 412
// instead of undoing a change the editor never saw.
function ifMatch(flag: FlagResponse) {
  return { "if-match": `"${String(flag.version)}"` };
}

interface SwitchRequest {
  flag: FlagResponse;
  environmentKey: string;
  on: boolean;
}

export function useSwitchFlag(projectKey: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ flag, environmentKey, on }: SwitchRequest) => {
      const path = { project_key: projectKey, flag_key: flag.key, environment_key: environmentKey };
      // Turning a flag off is the kill switch, and has to work whatever changed since the page
      // loaded. Turning it on starts serving its targeting, so only the targeting on screen.
      return on
        ? unwrap(
            client.POST(
              "/projects/{project_key}/flags/{flag_key}/environments/{environment_key}/enable",
              { params: { path, header: ifMatch(flag) } },
            ),
          )
        : unwrap(
            client.POST(
              "/projects/{project_key}/flags/{flag_key}/environments/{environment_key}/disable",
              { params: { path } },
            ),
          );
    },
    onSuccess: (flag) => {
      rememberFlag(queryClient, client, projectKey, flag);
    },
    onError: () => {
      refreshFlags(queryClient, client, projectKey);
    },
  });
}

export function useCreateFlag(projectKey: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateFlag) =>
      unwrap(
        client.POST("/projects/{project_key}/flags", {
          params: { path: { project_key: projectKey } },
          body,
        }),
      ),
    onSuccess: (flag) => {
      queryClient.setQueryData(flagQuery(client, projectKey, flag.key).queryKey, flag);
      void queryClient.invalidateQueries({ queryKey: flagsQuery(client, projectKey).queryKey });
    },
  });
}

interface DetailsRequest {
  flag: FlagResponse;
  name: string;
  description: string;
}

export function useChangeDetails(projectKey: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ flag, name, description }: DetailsRequest) =>
      unwrap(
        client.PATCH("/projects/{project_key}/flags/{flag_key}", {
          params: { path: { project_key: projectKey, flag_key: flag.key }, header: ifMatch(flag) },
          body: { name, description },
        }),
      ),
    onSuccess: (flag) => {
      rememberFlag(queryClient, client, projectKey, flag);
    },
    onError: () => {
      refreshFlags(queryClient, client, projectKey);
    },
  });
}

export function useArchiveFlag(projectKey: string) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (flag: FlagResponse) =>
      unwrap(
        client.POST("/projects/{project_key}/flags/{flag_key}/archive", {
          params: { path: { project_key: projectKey, flag_key: flag.key }, header: ifMatch(flag) },
        }),
      ),
    onSuccess: (flag) => {
      queryClient.removeQueries({ queryKey: flagQuery(client, projectKey, flag.key).queryKey });
      queryClient.setQueryData(flagsQuery(client, projectKey).queryKey, (flags) =>
        flags?.filter((listed) => listed.key !== flag.key),
      );
      void queryClient.invalidateQueries({
        queryKey: environmentsQuery(client, projectKey).queryKey,
        exact: true,
      });
    },
    onError: () => {
      refreshFlags(queryClient, client, projectKey);
    },
  });
}

// Every edit answers with the whole flag, so both the flag and the list it appears in are updated
// from that. The environments' ruleset versions moved on with it.
function rememberFlag(
  queryClient: QueryClient,
  client: ApiClient,
  projectKey: string,
  flag: FlagResponse,
) {
  queryClient.setQueryData(flagQuery(client, projectKey, flag.key).queryKey, flag);
  queryClient.setQueryData(flagsQuery(client, projectKey).queryKey, (flags) =>
    flags?.map((listed) => (listed.key === flag.key ? flag : listed)),
  );
  void queryClient.invalidateQueries({
    queryKey: environmentsQuery(client, projectKey).queryKey,
    exact: true,
  });
}

// After a failed edit what is on screen may be out of date; after a 412 it certainly is. The
// flag pages show the refreshed flag, and the error says what happened.
function refreshFlags(queryClient: QueryClient, client: ApiClient, projectKey: string) {
  void queryClient.invalidateQueries({ queryKey: flagsQuery(client, projectKey).queryKey });
}
