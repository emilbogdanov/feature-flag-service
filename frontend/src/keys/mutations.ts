import { useMutation, useQueryClient } from "@tanstack/react-query";

import { unwrap } from "../api/client";
import { apiKeysQuery } from "../api/queries";
import type { IssueApiKey } from "../api/schema";
import { useApiClient } from "../session/session-context";

export function useIssueApiKey() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: IssueApiKey) => unwrap(client.POST("/api-keys", { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: apiKeysQuery(client).queryKey });
    },
  });
}

export function useRevokeApiKey() {
  const client = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) =>
      unwrap(client.POST("/api-keys/{key_id}/revoke", { params: { path: { key_id: keyId } } })),
    onSuccess: (revoked) => {
      queryClient.setQueryData(apiKeysQuery(client).queryKey, (keys) =>
        keys?.map((key) => (key.id === revoked.id ? revoked : key)),
      );
    },
  });
}
