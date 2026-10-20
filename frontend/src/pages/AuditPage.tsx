import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useId } from "react";
import { useSearchParams } from "react-router";

import { auditQuery, projectsQuery } from "../api/queries";
import { AuditEntry } from "../audit/AuditEntry";
import styles from "../audit/AuditEntry.module.css";
import { Button } from "../components/Button";
import { cx } from "../components/cx";
import { ErrorNotice } from "../components/ErrorNotice";
import form from "../components/form.module.css";
import { useApiClient } from "../session/session-context";
import page from "./page.module.css";

export function AuditPage() {
  const client = useApiClient();
  const id = useId();
  // The filter lives in the address, so a project's history can be linked to.
  const [search, setSearch] = useSearchParams();
  const projectKey = search.get("project");
  const projects = useQuery(projectsQuery(client));
  const log = useInfiniteQuery(auditQuery(client, projectKey));
  const entries = log.data?.pages.flatMap((loaded) => loaded.entries) ?? [];

  return (
    <>
      <div className={page.heading}>
        <h1>Audit log</h1>
        <p className={page.subtitle}>Every change, newest first, with the key that made it.</p>
      </div>
      <div className={page.sections}>
        <div className={cx(form.field, page.filter)}>
          <label htmlFor={`${id}-project`} className={form.label}>
            Project
          </label>
          <select
            id={`${id}-project`}
            className={cx(form.input, form.mono)}
            value={projectKey ?? ""}
            onChange={(event) => {
              setSearch(event.target.value === "" ? {} : { project: event.target.value });
            }}
          >
            <option value="">All projects</option>
            {projects.data?.map((project) => (
              <option key={project.key} value={project.key}>
                {project.key}
              </option>
            ))}
          </select>
        </div>

        <section className={page.section} aria-label="Changes">
          {log.isPending ? (
            <p className={page.status}>Loading changes…</p>
          ) : log.isError && entries.length === 0 ? (
            <ErrorNotice error={log.error} onRetry={() => void log.refetch()} />
          ) : entries.length === 0 ? (
            <p className={page.muted}>Nothing has changed here yet.</p>
          ) : (
            <ol className={styles.entries}>
              {entries.map((entry) => (
                <AuditEntry key={entry.id} entry={entry} shownProject={projectKey} />
              ))}
            </ol>
          )}
          {log.isFetchNextPageError && (
            <ErrorNotice error={log.error} onRetry={() => void log.fetchNextPage()} />
          )}
          {log.hasNextPage && !log.isFetchNextPageError && (
            <div>
              <Button disabled={log.isFetchingNextPage} onClick={() => void log.fetchNextPage()}>
                {log.isFetchingNextPage ? "Loading older changes…" : "Show older changes"}
              </Button>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
