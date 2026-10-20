import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { ApiError } from "../api/client";
import { environmentsQuery, projectQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { formatDate } from "../format";
import { useApiClient } from "../session/session-context";
import styles from "./page.module.css";

export function ProjectPage() {
  const { projectKey = "" } = useParams();
  const client = useApiClient();
  const project = useQuery(projectQuery(client, projectKey));
  const environments = useQuery(environmentsQuery(client, projectKey));

  if (project.error instanceof ApiError && project.error.code === "project_not_found") {
    return (
      <div className={styles.empty}>
        <h1>No such project</h1>
        <p>
          There is no project with the key <code>{projectKey}</code>.{" "}
          <Link to="/">See all projects</Link>
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
          <li aria-current="page">{project.data?.name ?? projectKey}</li>
        </ol>
      </nav>
      <div className={styles.heading}>
        <h1>{project.data?.name ?? projectKey}</h1>
        <p className={styles.subtitle}>
          <code>{projectKey}</code>
        </p>
      </div>
      {project.isError && (
        <ErrorNotice error={project.error} onRetry={() => void project.refetch()} />
      )}

      <section className={styles.section} aria-labelledby="environments">
        <h2 id="environments">Environments</h2>
        {environments.isPending ? (
          <p className={styles.status}>Loading environments…</p>
        ) : environments.isError ? (
          <ErrorNotice error={environments.error} onRetry={() => void environments.refetch()} />
        ) : (
          <table>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Key</th>
                <th scope="col" className="numeric">
                  Ruleset version
                </th>
                <th scope="col">Created</th>
              </tr>
            </thead>
            <tbody>
              {environments.data.map((environment) => (
                <tr key={environment.key}>
                  <td>{environment.name}</td>
                  <td>
                    <code>{environment.key}</code>
                  </td>
                  <td className="numeric">{environment.ruleset_version}</td>
                  <td className="date">{formatDate(environment.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
