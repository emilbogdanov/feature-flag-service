import { Link, NavLink, Outlet, useLocation } from "react-router";

import { Button } from "../components/Button";
import { cx } from "../components/cx";
import { useSession } from "../session/session-context";
import styles from "./Layout.module.css";

export function Layout() {
  const { signOut } = useSession();
  // Every project page belongs under Projects, though only "/" is its link.
  const { pathname } = useLocation();
  const inProjects = pathname === "/" || pathname.startsWith("/projects/");

  return (
    <>
      <header className={styles.header}>
        <div className={styles.bar}>
          <Link to="/" className={styles.wordmark}>
            Flagstaff
          </Link>
          <nav aria-label="Sections" className={styles.nav}>
            <Link
              to="/"
              className={cx(styles.section, inProjects && styles.current)}
              aria-current={inProjects ? "page" : undefined}
            >
              Projects
            </Link>
            <NavLink
              to="/api-keys"
              className={({ isActive }) => cx(styles.section, isActive && styles.current)}
            >
              API keys
            </NavLink>
            <NavLink
              to="/audit"
              className={({ isActive }) => cx(styles.section, isActive && styles.current)}
            >
              Audit log
            </NavLink>
          </nav>
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
