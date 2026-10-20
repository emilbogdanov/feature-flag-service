import type { ComponentProps } from "react";

import styles from "./Button.module.css";
import { cx } from "./cx";

interface ButtonProps extends ComponentProps<"button"> {
  variant?: "primary" | "quiet";
}

export function Button({ variant = "quiet", className, type = "button", ...props }: ButtonProps) {
  return (
    <button type={type} className={cx(styles.button, styles[variant], className)} {...props} />
  );
}
