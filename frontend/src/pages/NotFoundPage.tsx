import { Link } from "react-router";

import styles from "./page.module.css";

export function NotFoundPage() {
  return (
    <div className={styles.empty}>
      <h1>Page not found</h1>
      <p>
        Nothing in the dashboard lives at this address. <Link to="/">See all projects</Link>
      </p>
    </div>
  );
}
