import { useRouteError } from "react-router";

import { ErrorNotice } from "../components/ErrorNotice";
import styles from "./page.module.css";

// Shown when rendering a page throws: a bug, not a failed request, which pages show themselves.
export function RouteErrorPage() {
  const error = useRouteError();
  return (
    <main className={styles.crashed}>
      <h1>This page stopped working</h1>
      <ErrorNotice
        error={error}
        onRetry={() => {
          window.location.reload();
        }}
      />
    </main>
  );
}
