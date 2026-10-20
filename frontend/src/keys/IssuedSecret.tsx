import { useId, useRef, useState } from "react";

import type { IssuedApiKeyResponse } from "../api/schema";
import { Button } from "../components/Button";
import { ButtonLink } from "../components/ButtonLink";
import { cx } from "../components/cx";
import form from "../components/form.module.css";
import page from "../pages/page.module.css";

interface IssuedSecretProps {
  issued: IssuedApiKeyResponse;
}

export function IssuedSecret({ issued }: IssuedSecretProps) {
  const id = useId();
  const field = useRef<HTMLInputElement>(null);
  const [copied, setCopied] = useState<boolean | null>(null);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(issued.secret);
      setCopied(true);
    } catch {
      // No clipboard outside a secure context: select it, so copying by hand is one keystroke.
      field.current?.select();
      setCopied(false);
    }
  };

  return (
    <div className={form.form}>
      <div className={page.notice} role="status">
        <p>
          {issued.name} is ready. Copy its secret now: Flagstaff keeps only a hash of it, so it
          can&apos;t be shown again.
        </p>
      </div>
      <div className={form.field}>
        <label htmlFor={`${id}-secret`} className={form.label}>
          Secret
        </label>
        <input
          ref={field}
          id={`${id}-secret`}
          className={cx(form.input, form.mono)}
          value={issued.secret}
          readOnly
          spellCheck={false}
          onFocus={(event) => {
            event.target.select();
          }}
        />
        {copied === true && <p className={form.hint}>Copied to the clipboard.</p>}
        {copied === false && (
          <p className={form.hint}>The browser won&apos;t allow copying here; it is selected.</p>
        )}
      </div>
      <div className={form.actions}>
        <Button variant="primary" onClick={() => void copy()}>
          Copy secret
        </Button>
        <ButtonLink to="/api-keys">Done</ButtonLink>
      </div>
    </div>
  );
}
