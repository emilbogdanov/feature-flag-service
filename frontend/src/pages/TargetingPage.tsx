import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { hasCode } from "../api/errors";
import { environmentsQuery, flagQuery, projectQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { TargetingForm } from "../flags/TargetingForm";
import { useApiClient } from "../session/session-context";
import styles from "./page.module.css";

export function TargetingPage() {
  const { projectKey = "", flagKey = "", environmentKey = "" } = useParams();
  const client = useApiClient();
  const project = useQuery(projectQuery(client, projectKey));
  const flag = useQuery(flagQuery(client, projectKey, flagKey));
  const environments = useQuery(environmentsQuery(client, projectKey));
  const projectPath = `/projects/${encodeURIComponent(projectKey)}`;
  const flagPath = `${projectPath}/flags/${encodeURIComponent(flagKey)}`;
  const environment = environments.data?.find((candidate) => candidate.key === environmentKey);

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
  if (environments.isSuccess && environment === undefined) {
    return (
      <div className={styles.empty}>
        <h1>No such environment</h1>
        <p>
          This project has no environment with the key <code>{environmentKey}</code>.{" "}
          <Link to={flagPath}>Back to the flag</Link>
        </p>
      </div>
    );
  }

  const error = flag.error ?? environments.error;
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
          <li>
            <Link to={flagPath}>{flag.data?.name ?? flagKey}</Link>
          </li>
          <li aria-current="page">{environment?.name ?? environmentKey}</li>
        </ol>
      </nav>
      {error !== null ? (
        <ErrorNotice
          error={error}
          onRetry={() => {
            void flag.refetch();
            void environments.refetch();
          }}
        />
      ) : flag.data === undefined || environment === undefined ? (
        <p className={styles.status}>Loading the flag…</p>
      ) : (
        <>
          <div className={styles.heading}>
            <h1>
              {flag.data.name} in {environment.name}
            </h1>
            <p className={styles.subtitle}>
              Rules are tried from the top. The first one a user matches decides what they get.
            </p>
          </div>
          {flag.data.archived_at !== null ? (
            <p className={styles.notice}>
              This flag is archived, so its targeting can&apos;t change.
            </p>
          ) : (
            <TargetingForm
              key={`${flag.data.key}/${environment.key}`}
              projectKey={projectKey}
              flag={flag.data}
              environment={environment}
            />
          )}
        </>
      )}
    </>
  );
}
