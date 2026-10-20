import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useId, useState } from "react";
import { Link } from "react-router";

import { environmentsQuery, projectsQuery } from "../api/queries";
import type { ApiKeyKind } from "../api/schema";
import { Button } from "../components/Button";
import { cx } from "../components/cx";
import { ErrorNotice } from "../components/ErrorNotice";
import form from "../components/form.module.css";
import { IssuedSecret } from "../keys/IssuedSecret";
import { useIssueApiKey } from "../keys/mutations";
import { useApiClient } from "../session/session-context";
import styles from "./page.module.css";

export function NewApiKeyPage() {
  const client = useApiClient();
  const issue = useIssueApiKey();
  const id = useId();
  const [kind, setKind] = useState<ApiKeyKind>("sdk");
  const [name, setName] = useState("");
  const [project, setProject] = useState("");
  const [environment, setEnvironment] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const projects = useQuery({ ...projectsQuery(client), enabled: kind === "sdk" });
  const environments = useQuery({
    ...environmentsQuery(client, project),
    enabled: kind === "sdk" && project !== "",
  });

  const errors = {
    name:
      name.trim() === "" ? "Say who or what will use the key, such as checkout-api." : undefined,
    project: kind === "sdk" && project === "" ? "Choose the project it reads." : undefined,
    environment:
      kind === "sdk" && environment === "" ? "Choose the environment it reads." : undefined,
  };
  const shown = (error: string | undefined) => (submitted ? error : undefined);

  const breadcrumb = (
    <nav aria-label="Breadcrumb" className={styles.breadcrumb}>
      <ol>
        <li>
          <Link to="/api-keys">API keys</Link>
        </li>
        <li aria-current="page">New key</li>
      </ol>
    </nav>
  );

  if (issue.isSuccess) {
    return (
      <>
        {breadcrumb}
        <div className={styles.heading}>
          <h1>Key issued</h1>
        </div>
        <IssuedSecret issued={issue.data} />
      </>
    );
  }

  return (
    <>
      {breadcrumb}
      <div className={styles.heading}>
        <h1>Issue a key</h1>
      </div>
      <form
        className={form.form}
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          setSubmitted(true);
          if (Object.values(errors).some((error) => error !== undefined)) {
            return;
          }
          issue.mutate(
            kind === "admin"
              ? { kind, name: name.trim() }
              : { kind, name: name.trim(), project, environment },
          );
        }}
      >
        <fieldset className={form.fieldset}>
          <legend className={form.legend}>Kind</legend>
          <label className={form.choice}>
            <input
              type="radio"
              name={`${id}-kind`}
              checked={kind === "sdk"}
              onChange={() => {
                setKind("sdk");
              }}
            />
            SDK key, for an app that reads one environment&apos;s flags
          </label>
          <label className={form.choice}>
            <input
              type="radio"
              name={`${id}-kind`}
              checked={kind === "admin"}
              onChange={() => {
                setKind("admin");
              }}
            />
            Admin key, for a person or a tool that changes flags
          </label>
        </fieldset>

        <Field id={`${id}-name`} label="Name" error={shown(errors.name)}>
          <input
            id={`${id}-name`}
            className={form.input}
            value={name}
            autoComplete="off"
            aria-invalid={shown(errors.name) !== undefined}
            aria-describedby={shown(errors.name) && `${id}-name-error`}
            onChange={(event) => {
              setName(event.target.value);
            }}
          />
        </Field>

        {kind === "sdk" && (
          <div className={form.row}>
            <Field id={`${id}-project`} label="Project" error={shown(errors.project)}>
              <select
                id={`${id}-project`}
                className={cx(form.input, form.mono)}
                value={project}
                aria-invalid={shown(errors.project) !== undefined}
                aria-describedby={shown(errors.project) && `${id}-project-error`}
                onChange={(event) => {
                  setProject(event.target.value);
                  setEnvironment("");
                }}
              >
                <option value="" disabled>
                  {projects.isPending ? "Loading projects…" : "Choose a project"}
                </option>
                {projects.data?.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.key}
                  </option>
                ))}
              </select>
            </Field>
            <Field id={`${id}-environment`} label="Environment" error={shown(errors.environment)}>
              <select
                id={`${id}-environment`}
                className={cx(form.input, form.mono)}
                value={environment}
                disabled={project === ""}
                aria-invalid={shown(errors.environment) !== undefined}
                aria-describedby={shown(errors.environment) && `${id}-environment-error`}
                onChange={(event) => {
                  setEnvironment(event.target.value);
                }}
              >
                <option value="" disabled>
                  Choose an environment
                </option>
                {environments.data?.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.key}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        )}

        {(projects.isError || environments.isError) && (
          <ErrorNotice error={projects.error ?? environments.error} />
        )}
        {issue.isError && <ErrorNotice error={issue.error} />}
        <div className={form.actions}>
          <Button type="submit" variant="primary" disabled={issue.isPending}>
            {issue.isPending ? "Issuing…" : "Issue key"}
          </Button>
          <Link to="/api-keys">Cancel</Link>
        </div>
      </form>
    </>
  );
}

interface FieldProps {
  id: string;
  label: string;
  error: string | undefined;
  children: ReactNode;
}

function Field({ id, label, error, children }: FieldProps) {
  return (
    <div className={form.field}>
      <label htmlFor={id} className={form.label}>
        {label}
      </label>
      {children}
      {error !== undefined && (
        <p id={`${id}-error`} className={form.error}>
          {error}
        </p>
      )}
    </div>
  );
}
