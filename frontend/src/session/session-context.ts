import { createContext, useContext } from "react";

import type { ApiClient } from "../api/client";

export interface Session {
  // The client for the signed-in admin key, or null before sign-in.
  client: ApiClient | null;
  // Why the last session ended, when it was not the user's choice.
  notice: string | null;
  signIn: (adminKey: string) => void;
  signOut: (notice?: string) => void;
}

export const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (session === null) {
    throw new Error("useSession needs a SessionProvider above it");
  }
  return session;
}

// For pages under RequireSession, which only renders them while signed in.
export function useApiClient(): ApiClient {
  const { client } = useSession();
  if (client === null) {
    throw new Error("useApiClient needs a signed-in session");
  }
  return client;
}
