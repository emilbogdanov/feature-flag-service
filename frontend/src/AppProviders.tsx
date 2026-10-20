import { type QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useCallback, useEffect, useState } from "react";

import { isUnauthorized } from "./api/errors";
import { createQueryClient } from "./api/query-client";
import { SessionProvider } from "./session/SessionProvider";
import { useSession } from "./session/session-context";

const REJECTED_KEY_NOTICE =
  "The API stopped accepting your admin key. It may have been revoked; sign in with another.";

interface AppProvidersProps {
  children: ReactNode;
  queryClient?: QueryClient;
}

export function AppProviders({ children, queryClient: given }: AppProvidersProps) {
  const [queryClient] = useState(() => given ?? createQueryClient());
  // Nothing fetched with one key may be shown to whoever signs in next.
  const clearCache = useCallback(() => {
    queryClient.clear();
  }, [queryClient]);

  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider onSignOut={clearCache}>
        <SignOutWhenKeyRejected />
        {children}
      </SessionProvider>
    </QueryClientProvider>
  );
}

// A key revoked while the dashboard is open fails every request from then on with 401. The first
// one ends the session, so the next screen is the sign-in form rather than a wall of errors. While
// signed out, a 401 is the sign-in form's own answer and is left to it.
function SignOutWhenKeyRejected() {
  const queryClient = useQueryClient();
  const { client, signOut } = useSession();
  const signedIn = client !== null;

  useEffect(() => {
    if (!signedIn) {
      return undefined;
    }
    const signOutIfRejected = (error: unknown) => {
      if (isUnauthorized(error)) {
        signOut(REJECTED_KEY_NOTICE);
      }
    };
    const unsubscribeQueries = queryClient.getQueryCache().subscribe((event) => {
      if (event.type === "updated" && event.action.type === "error") {
        signOutIfRejected(event.action.error);
      }
    });
    const unsubscribeMutations = queryClient.getMutationCache().subscribe((event) => {
      if (event.type === "updated" && event.action.type === "error") {
        signOutIfRejected(event.action.error);
      }
    });
    return () => {
      unsubscribeQueries();
      unsubscribeMutations();
    };
  }, [queryClient, signOut, signedIn]);

  return null;
}
