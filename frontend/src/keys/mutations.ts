import { useMutation, useQueryClient } from "@tanstack/react-query";

import { unwrap } from "../api/client";
import { apiKeysQuery } from "../api/queries";
import { useApiClient } from "../session/session-context";

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
