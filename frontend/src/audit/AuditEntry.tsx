import type { AuditEntryResponse } from "../api/schema";
import { describeAction, formatTime } from "./describe";
import styles from "./AuditEntry.module.css";

interface AuditEntryProps {
  entry: AuditEntryResponse;
  // The project the log is filtered to, if any.
  shownProject: string | null;
}

export function AuditEntry({ entry, shownProject }: AuditEntryProps) {
  const { verb, subject, place } = describeAction(entry, shownProject);
  const hasChanges = Object.keys(entry.changes).length > 0;

  return (
    <li className={styles.entry}>
      <time dateTime={entry.at} className={styles.time}>
        {formatTime(entry.at)}
      </time>
      <div className={styles.what}>
        <p>
          <span className={styles.actor}>{entry.actor.name}</span> {verb} <code>{subject}</code>
          {place !== null && (
            <>
              {" "}
              {place.preposition} <code>{place.path}</code>
            </>
          )}
        </p>
        {hasChanges && (
          <details className={styles.changes}>
            <summary>What changed</summary>
            <pre>
              <code>{JSON.stringify(entry.changes, null, 2)}</code>
            </pre>
          </details>
        )}
      </div>
    </li>
  );
}
