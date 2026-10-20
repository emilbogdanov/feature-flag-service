import { Link, Outlet } from "react-router";

import { Button } from "../components/Button";
import { useSession } from "../session/session-context";
import styles from "./Layout.module.css";

export function Layout() {
  const { signOut } = useSession();
  return (
    <>
      <header className={styles.header}>
        <div className={styles.bar}>
          <Link to="/" className={styles.wordmark}>
            Flagstaff
          </Link>
          <Button
            onClick={() => {
              signOut();
            }}
          >
            Sign out
          </Button>
        </div>
      </header>
      <main className={styles.main}>
        <Outlet />
      </main>
    </>
  );
}
