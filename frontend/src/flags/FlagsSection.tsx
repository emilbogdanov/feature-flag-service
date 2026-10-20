import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { flagsQuery } from "../api/queries";
import type { EnvironmentResponse } from "../api/schema";
import { ButtonLink } from "../components/ButtonLink";
import { ErrorNotice } from "../components/ErrorNotice";
import page from "../pages/page.module.css";
import { useApiClient } from "../session/session-context";
import { FlagSwitch } from "./FlagSwitch";
import styles from "./FlagsSection.module.css";
import { KIND_LABELS } from "./variants";

interface FlagsSectionProps {
  projectKey: string;
  environments: EnvironmentResponse[];
}

export function FlagsSection({ projectKey, environments }: FlagsSectionProps) {
  const flags = useQuery(flagsQuery(useApiClient(), projectKey));
  const [failure, setFailure] = useState<string | null>(null);
  const flagPath = (flagKey: string) =>
    `/projects/${encodeURIComponent(projectKey)}/flags/${encodeURIComponent(flagKey)}`;

  return (
    <section className={page.section} aria-labelledby="flags">
      <div className={styles.header}>
        <h2 id="flags">Flags</h2>
        <ButtonLink to={`/projects/${encodeURIComponent(projectKey)}/flags/new`}>
          New flag
        </ButtonLink>
      </div>
      {failure !== null && <ErrorNotice error={new Error(failure)} />}
      {flags.isPending ? (
        <p className={page.status}>Loading flags…</p>
      ) : flags.isError ? (
        <ErrorNotice error={flags.error} onRetry={() => void flags.refetch()} />
      ) : flags.data.length === 0 ? (
        <div className={page.empty}>
          <p>No flags yet.</p>
          <p className={page.muted}>
            A new flag starts off in every environment, so creating one changes nothing for users
            until you turn it on.
          </p>
        </div>
      ) : (
        <div className={styles.scroller}>
          <table>
            <thead>
              <tr>
                <th scope="col">Flag</th>
                <th scope="col">Kind</th>
                {environments.map((environment) => (
                  <th scope="col" key={environment.key}>
                    {environment.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {flags.data.map((flag) => (
                <tr key={flag.key}>
                  <td>
                    <span className={styles.flag}>
                      <Link to={flagPath(flag.key)}>{flag.name}</Link>
                      <code className={styles.key}>{flag.key}</code>
                    </span>
                  </td>
                  <td className={styles.kind}>{KIND_LABELS[flag.kind]}</td>
                  {environments.map((environment) => (
                    <td key={environment.key}>
                      <FlagSwitch
                        projectKey={projectKey}
                        flag={flag}
                        environment={environment}
                        onFailure={setFailure}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
