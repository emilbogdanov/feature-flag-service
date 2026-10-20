import { useId, useState } from "react";

import type { FlagResponse } from "../api/schema";
import { Button } from "../components/Button";
import { ErrorNotice } from "../components/ErrorNotice";
import form from "../components/form.module.css";
import page from "../pages/page.module.css";
import { useChangeDetails } from "./mutations";

interface FlagDetailsProps {
  projectKey: string;
  flag: FlagResponse;
  editable: boolean;
}

export function FlagDetails({ projectKey, flag, editable }: FlagDetailsProps) {
  const [editing, setEditing] = useState(false);

  if (editing) {
    return (
      <DetailsForm
        projectKey={projectKey}
        flag={flag}
        onDone={() => {
          setEditing(false);
        }}
      />
    );
  }
  return (
    <div className={page.details}>
      {flag.description === "" ? (
        <p className={page.muted}>No description.</p>
      ) : (
        <p>{flag.description}</p>
      )}
      {editable && (
        <Button
          onClick={() => {
            setEditing(true);
          }}
        >
          Edit name and description
        </Button>
      )}
    </div>
  );
}

interface DetailsFormProps {
  projectKey: string;
  flag: FlagResponse;
  onDone: () => void;
}

function DetailsForm({ projectKey, flag, onDone }: DetailsFormProps) {
  const change = useChangeDetails(projectKey);
  const id = useId();
  const [name, setName] = useState(flag.name);
  const [description, setDescription] = useState(flag.description);
  const nameMissing = name.trim() === "";

  return (
    <form
      className={form.form}
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        if (nameMissing) {
          return;
        }
        change.mutate(
          { flag, name: name.trim(), description: description.trim() },
          { onSuccess: onDone },
        );
      }}
    >
      <div className={form.field}>
        <label htmlFor={`${id}-name`} className={form.label}>
          Name
        </label>
        <input
          id={`${id}-name`}
          className={form.input}
          value={name}
          aria-invalid={nameMissing}
          aria-describedby={nameMissing ? `${id}-name-error` : undefined}
          onChange={(event) => {
            setName(event.target.value);
          }}
        />
        {nameMissing && (
          <p id={`${id}-name-error`} className={form.error}>
            Give the flag a name.
          </p>
        )}
      </div>
      <div className={form.field}>
        <label htmlFor={`${id}-description`} className={form.label}>
          Description
        </label>
        <textarea
          id={`${id}-description`}
          className={form.input}
          value={description}
          onChange={(event) => {
            setDescription(event.target.value);
          }}
        />
      </div>
      {change.isError && <ErrorNotice error={change.error} />}
      <div className={form.actions}>
        <Button type="submit" variant="primary" disabled={change.isPending}>
          {change.isPending ? "Saving…" : "Save name and description"}
        </Button>
        <Button onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}
