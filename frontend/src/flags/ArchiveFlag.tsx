import { useState } from "react";
import { useNavigate } from "react-router";

import type { FlagResponse } from "../api/schema";
import { Button } from "../components/Button";
import { ErrorNotice } from "../components/ErrorNotice";
import form from "../components/form.module.css";
import page from "../pages/page.module.css";
import { useArchiveFlag } from "./mutations";

interface ArchiveFlagProps {
  projectKey: string;
  flag: FlagResponse;
}

export function ArchiveFlag({ projectKey, flag }: ArchiveFlagProps) {
  const archive = useArchiveFlag(projectKey);
  const navigate = useNavigate();
  const [confirming, setConfirming] = useState(false);

  return (
    <section className={page.section} aria-labelledby="archive">
      <h2 id="archive">Archive</h2>
      <p>
        Archiving takes the flag out of every environment, so code asking for{" "}
        <code>{flag.key}</code> gets the default it was written with. It can&apos;t be undone, and
        the key stays taken.
      </p>
      {archive.isError && <ErrorNotice error={archive.error} />}
      <div className={form.actions}>
        {confirming ? (
          <>
            <Button
              variant="danger"
              disabled={archive.isPending}
              onClick={() => {
                archive.mutate(flag, {
                  onSuccess: () => {
                    void navigate(`/projects/${encodeURIComponent(projectKey)}`);
                  },
                });
              }}
            >
              {archive.isPending ? "Archiving…" : `Archive ${flag.name} for good`}
            </Button>
            <Button
              onClick={() => {
                setConfirming(false);
              }}
            >
              Keep the flag
            </Button>
          </>
        ) : (
          <Button
            onClick={() => {
              setConfirming(true);
            }}
          >
            Archive flag
          </Button>
        )}
      </div>
    </section>
  );
}
