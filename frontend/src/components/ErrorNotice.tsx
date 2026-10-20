import { describeError } from "../api/errors";
import { Button } from "./Button";
import styles from "./ErrorNotice.module.css";

interface ErrorNoticeProps {
  error: unknown;
  onRetry?: () => void;
}

export function ErrorNotice({ error, onRetry }: ErrorNoticeProps) {
  return (
    <div role="alert" className={styles.notice}>
      <p>{describeError(error)}</p>
      {onRetry && <Button onClick={onRetry}>Try again</Button>}
    </div>
  );
}
