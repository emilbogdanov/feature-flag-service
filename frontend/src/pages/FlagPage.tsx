import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { hasCode } from "../api/errors";
import { environmentsQuery, flagQuery, projectQuery } from "../api/queries";
import type { EnvironmentResponse, FlagResponse } from "../api/schema";
import { ErrorNotice } from "../components/ErrorNotice";
import { ArchiveFlag } from "../flags/ArchiveFlag";
import { FlagDetails } from "../flags/FlagDetails";
import { FlagSwitch } from "../flags/FlagSwitch";
import { describeServe } from "../flags/serve";
import { KIND_LABELS, formatValue } from "../flags/variants";
import { formatDate } from "../format";
import { useApiClient } from "../session/session-context";
import styles from "./page.module.css";

export function FlagPage() {
  const { projectKey = "", flagKey = "" } = useParams();
  const client = useApiClient();
  const project = useQuery(projectQuery(client, projectKey));
  const flag = useQuery(flagQuery(client, projectKey, flagKey));
  const environments = useQuery(environmentsQuery(client, projectKey));
  const projectPath = `/projects/${encodeURIComponent(projectKey)}`;

  if (hasCode(flag.error, "flag_not_found") || hasCode(flag.error, "project_not_found")) {
    return (
      <div className={styles.empty}>
        <h1>No such flag</h1>
        <p>
          There is no flag with the key <code>{flagKey}</code> in this project.{" "}
          <Link to={projectPath}>See its flags</Link>
        </p>
      </div>
    );
  }

  return (
    <>
      <nav aria-label="Breadcrumb" className={styles.breadcrumb}>
        <ol>
          <li>
            <Link to="/">Projects</Link>
          </li>
          <li>
            <Link to={projectPath}>{project.data?.name ?? projectKey}</Link>
          </li>
          <li aria-current="page">{flag.data?.name ?? flagKey}</li>
        </ol>
      </nav>
      {flag.isPending ? (
        <p className={styles.status}>Loading the flag…</p>
      ) : flag.isError ? (
        <ErrorNotice error={flag.error} onRetry={() => void flag.refetch()} />
      ) : (
        <Flag
          projectKey={projectKey}
          flag={flag.data}
          environments={environments.data}
          environmentsError={environments.error}
        />
      )}
    </>
  );
}

interface FlagProps {
  projectKey: string;
  flag: FlagResponse;
  environments: EnvironmentResponse[] | undefined;
  environmentsError: unknown;
}

function Flag({ projectKey, flag, environments, environmentsError }: FlagProps) {
  const [failure, setFailure] = useState<string | null>(null);
  const archived = flag.archived_at !== null;

  return (
    <>
      <div className={styles.heading}>
        <h1>{flag.name}</h1>
        <p className={styles.subtitle}>
          <code>{flag.key}</code>, a {KIND_LABELS[flag.kind].toLowerCase()} flag
        </p>
      </div>
      <div className={styles.sections}>
        {flag.archived_at !== null && (
          <p className={styles.notice}>
            Archived on {formatDate(flag.archived_at)}. No environment serves it, and it can no
            longer be changed.
          </p>
        )}
        <FlagDetails projectKey={projectKey} flag={flag} editable={!archived} />

        <section className={styles.section} aria-labelledby="targeting">
          <h2 id="targeting">Environments</h2>
          {failure !== null && <ErrorNotice error={new Error(failure)} />}
          {environments === undefined ? (
            environmentsError ? (
              <ErrorNotice error={environmentsError} />
            ) : (
              <p className={styles.status}>Loading environments…</p>
            )
          ) : (
            <table>
              <thead>
                <tr>
                  <th scope="col">Environment</th>
                  <th scope="col">State</th>
                  <th scope="col">When off</th>
                  <th scope="col" className="numeric">
                    Rules
                  </th>
                  <th scope="col">Everyone else</th>
                </tr>
              </thead>
              <tbody>
                {environments.map((environment) => {
                  const targeting = flag.environments[environment.key];
                  return (
                    <tr key={environment.key}>
                      <th scope="row">{environment.name}</th>
                      <td>
                        {archived ? (
                          "Archived"
                        ) : (
                          <FlagSwitch
                            projectKey={projectKey}
                            flag={flag}
                            environment={environment}
                            onFailure={setFailure}
                          />
                        )}
                      </td>
                      <td>
                        <code>{targeting?.off_variant}</code>
                      </td>
                      <td className="numeric">{targeting?.rules?.length ?? 0}</td>
                      <td>{targeting && <code>{describeServe(targeting.fallthrough)}</code>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>

        <section className={styles.section} aria-labelledby="variants">
          <h2 id="variants">Variants</h2>
          <table>
            <thead>
              <tr>
                <th scope="col">Key</th>
                <th scope="col">Value</th>
              </tr>
            </thead>
            <tbody>
              {flag.variants.map((variant) => (
                <tr key={variant.key}>
                  <td>
                    <code>{variant.key}</code>
                  </td>
                  <td>
                    <code className={styles.value}>{formatValue(flag.kind, variant.value)}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        {!archived && <ArchiveFlag projectKey={projectKey} flag={flag} />}
      </div>
    </>
  );
}
