import type { ComponentProps } from "react";

import styles from "./Button.module.css";

interface ButtonProps extends ComponentProps<"button"> {
  variant?: "primary" | "quiet";
}

export function Button({ variant = "quiet", className, type = "button", ...props }: ButtonProps) {
  const classes = [styles.button, styles[variant], className].filter(Boolean).join(" ");
  return <button type={type} className={classes} {...props} />;
}
