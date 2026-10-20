import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { projectsQuery } from "../api/queries";
import { ErrorNotice } from "../components/ErrorNotice";
import { formatDate } from "../format";
import { useApiClient } from "../session/session-context";
import styles from "./page.module.css";

export function ProjectsPage() {
  const projects = useQuery(projectsQuery(useApiClient()));

  return (
    <>
      <div className={styles.heading}>
        <h1>Projects</h1>
      </div>
      {projects.isPending ? (
        <p className={styles.status}>Loading projects…</p>
      ) : projects.isError ? (
        <ErrorNotice error={projects.error} onRetry={() => void projects.refetch()} />
      ) : projects.data.length === 0 ? (
        <div className={styles.empty}>
          <p>No projects yet.</p>
          <p className={styles.muted}>
            Create one through the API with <code>POST /projects</code>, giving it a key and a name.
            It starts with dev, staging and prod environments.
          </p>
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Key</th>
              <th scope="col">Created</th>
            </tr>
          </thead>
          <tbody>
            {projects.data.map((project) => (
              <tr key={project.key}>
                <td>
                  <Link to={`/projects/${encodeURIComponent(project.key)}`}>{project.name}</Link>
                </td>
                <td>
                  <code>{project.key}</code>
                </td>
                <td className="date">{formatDate(project.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
