import { Link, type LinkProps } from "react-router";

import styles from "./Button.module.css";
import { cx } from "./cx";

interface ButtonLinkProps extends LinkProps {
  variant?: "primary" | "quiet";
}

// A link that looks like a button, for actions that are a page of their own.
export function ButtonLink({ variant = "quiet", className, ...props }: ButtonLinkProps) {
  return <Link className={cx(styles.button, styles[variant], styles.link, className)} {...props} />;
}
