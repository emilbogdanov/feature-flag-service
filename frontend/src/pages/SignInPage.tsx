import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { type Location, Navigate, useLocation, useNavigate } from "react-router";

import { ApiError, createApiClient, unwrap } from "../api/client";
import { describeError } from "../api/errors";
import { projectsQuery } from "../api/queries";
import { Button } from "../components/Button";
import { ErrorNotice } from "../components/ErrorNotice";
import { useSession } from "../session/session-context";
import styles from "./SignInPage.module.css";

export function SignInPage() {
  const { client, notice, signIn } = useSession();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const returnTo = returnPath(useLocation());
  const [adminKey, setAdminKey] = useState("");
  const keyId = useId();
  const hintId = useId();

  // The project list is the first thing every signed-in page needs, and the cheapest request that
  // only an admin key may make, so it doubles as the check that the key works.
  const check = useMutation({
    mutationFn: async (candidate: string) => {
      const client = createApiClient({ baseUrl: window.location.origin, adminKey: candidate });
      const projects = await unwrap(client.GET("/projects"));
      return { candidate, client, projects };
    },
    onSuccess: ({ candidate, client, projects }) => {
      signIn(candidate);
      queryClient.setQueryData(projectsQuery(client).queryKey, projects);
      void navigate(returnTo, { replace: true });
    },
  });

  if (client !== null && !check.isSuccess) {
    return <Navigate to={returnTo} replace />;
  }

  return (
    <main className={styles.page}>
      <div className={styles.panel}>
        <h1 className={styles.wordmark}>Flagstaff</h1>
        {notice !== null && !check.isPending && <ErrorNotice error={new Error(notice)} />}
        <form
          className={styles.form}
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            const candidate = adminKey.trim();
            if (candidate !== "") {
              check.mutate(candidate);
            }
          }}
        >
          <div className={styles.field}>
            <label htmlFor={keyId} className={styles.label}>
              Admin key
            </label>
            <input
              id={keyId}
              name="admin-key"
              type="password"
              className={styles.input}
              value={adminKey}
              onChange={(event) => {
                setAdminKey(event.target.value);
              }}
              autoComplete="off"
              spellCheck={false}
              required
              aria-describedby={hintId}
              aria-invalid={check.isError}
            />
            <p id={hintId} className={styles.hint}>
              The first admin key comes from the server:{" "}
              <code>flagstaff-server create-admin-key --name you</code>. It stays in this tab and is
              forgotten when the tab closes.
            </p>
          </div>
          {check.isError && (
            <p role="alert" className={styles.error}>
              {signInFailure(check.error)}
            </p>
          )}
          <Button
            type="submit"
            variant="primary"
            className={styles.submit}
            disabled={check.isPending}
          >
            {check.isPending ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </div>
    </main>
  );
}

function signInFailure(error: unknown): string {
  if (error instanceof ApiError && error.status === 401) {
    return "The API doesn't accept this key. Check that it was copied whole and hasn't been revoked.";
  }
  if (error instanceof ApiError && error.status === 403) {
    return "This is an SDK key, which can only read rules. Signing in needs an admin key.";
  }
  return describeError(error);
}

function returnPath(location: Location): string {
  const from: unknown = (location.state as { from?: unknown } | null)?.from;
  if (typeof from === "object" && from !== null && "pathname" in from) {
    const { pathname, search = "" } = from as Partial<Location>;
    if (typeof pathname === "string" && pathname !== "/sign-in") {
      return pathname + search;
    }
  }
  return "/";
}
