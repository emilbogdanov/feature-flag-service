import { useState } from "react";

import { describeError } from "../api/errors";
import type { ApiKeyResponse } from "../api/schema";
import { Button } from "../components/Button";
import form from "../components/form.module.css";
import { useRevokeApiKey } from "./mutations";

interface RevokeKeyProps {
  apiKey: ApiKeyResponse;
}

export function RevokeKey({ apiKey }: RevokeKeyProps) {
  const revoke = useRevokeApiKey();
  const [confirming, setConfirming] = useState(false);

  if (!confirming) {
    return (
      <Button
        aria-label={`Revoke ${apiKey.name}`}
        onClick={() => {
          setConfirming(true);
        }}
      >
        Revoke
      </Button>
    );
  }
  return (
    <div className={form.fieldset}>
      <div className={form.actions}>
        <Button
          variant="danger"
          disabled={revoke.isPending}
          onClick={() => {
            revoke.mutate(apiKey.id);
          }}
        >
          {revoke.isPending ? "Revoking…" : `Revoke ${apiKey.name} now`}
        </Button>
        <Button
          onClick={() => {
            setConfirming(false);
            revoke.reset();
          }}
        >
          Keep it
        </Button>
      </div>
      {revoke.isError && (
        <p role="alert" className={form.error}>
          {describeError(revoke.error)}
        </p>
      )}
    </div>
  );
}
