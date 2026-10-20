import { useQuery } from "@tanstack/react-query";

import { apiKeysQuery } from "../api/queries";
import type { ApiKeyResponse } from "../api/schema";
import { ButtonLink } from "../components/ButtonLink";
import { ErrorNotice } from "../components/ErrorNotice";
import { formatDate } from "../format";
import { RevokeKey } from "../keys/RevokeKey";
import { useApiClient } from "../session/session-context";
import styles from "./page.module.css";

export function ApiKeysPage() {
  const keys = useQuery(apiKeysQuery(useApiClient()));

  return (
    <>
      <div className={styles.heading}>
        <h1>API keys</h1>
        <p className={styles.subtitle}>
          Admin keys can change everything, this dashboard included. SDK keys can only read the
          rules of one environment. Revoking the key you signed in with signs you out.
        </p>
      </div>
      <div className={styles.sections}>
        <div>
          <ButtonLink to="/api-keys/new" variant="primary">
            Issue a key
          </ButtonLink>
        </div>
        {keys.isPending ? (
          <p className={styles.status}>Loading keys…</p>
        ) : keys.isError ? (
          <ErrorNotice error={keys.error} onRetry={() => void keys.refetch()} />
        ) : (
          <div className={styles.scroller}>
            <table>
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Reads</th>
                  <th scope="col">Issued</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {keys.data.map((key) => (
                  <tr key={key.id}>
                    <th scope="row">{key.name}</th>
                    <td>
                      <Scope apiKey={key} />
                    </td>
                    <td className="date">{formatDate(key.created_at)}</td>
                    <td>
                      {key.revoked_at === null ? (
                        <RevokeKey apiKey={key} />
                      ) : (
                        <span className={styles.muted}>Revoked {formatDate(key.revoked_at)}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

function Scope({ apiKey }: { apiKey: ApiKeyResponse }) {
  if (apiKey.kind === "admin") {
    return <>Everything, as an admin key</>;
  }
  return (
    <>
      <code>{apiKey.environment}</code> of <code>{apiKey.project}</code>
    </>
  );
}
