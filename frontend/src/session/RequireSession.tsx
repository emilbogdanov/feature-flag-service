import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { useSession } from "./session-context";

export function RequireSession({ children }: { children: ReactNode }) {
  const { client } = useSession();
  const location = useLocation();
  if (client === null) {
    // Remembers the page asked for, so signing in lands there instead of on the project list.
    return <Navigate to="/sign-in" replace state={{ from: location }} />;
  }
  return children;
}
