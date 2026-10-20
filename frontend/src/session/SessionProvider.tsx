import { type ReactNode, useCallback, useMemo, useState } from "react";

import { createApiClient } from "../api/client";
import { type Session, SessionContext } from "./session-context";
import { forgetStoredKey, readStoredKey, storeKey } from "./storage";

interface SessionProviderProps {
  children: ReactNode;
  // Where the API answers. The dashboard is served from the same origin as the API.
  baseUrl?: string;
  onSignOut?: () => void;
}

export function SessionProvider({
  children,
  baseUrl = window.location.origin,
  onSignOut,
}: SessionProviderProps) {
  const [adminKey, setAdminKey] = useState(readStoredKey);
  const [notice, setNotice] = useState<string | null>(null);

  const client = useMemo(
    () => (adminKey === null ? null : createApiClient({ baseUrl, adminKey })),
    [adminKey, baseUrl],
  );

  const signIn = useCallback((key: string) => {
    storeKey(key);
    setAdminKey(key);
    setNotice(null);
  }, []);

  const signOut = useCallback(
    (reason?: string) => {
      forgetStoredKey();
      setAdminKey(null);
      setNotice(reason ?? null);
      onSignOut?.();
    },
    [onSignOut],
  );

  const session = useMemo<Session>(
    () => ({ client, notice, signIn, signOut }),
    [client, notice, signIn, signOut],
  );
  return <SessionContext value={session}>{children}</SessionContext>;
}
