import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { hasCode } from "../api/errors";
import { projectQuery } from "../api/queries";
import type { FlagKind } from "../api/schema";
import { Button } from "../components/Button";
import { cx } from "../components/cx";
import { ErrorNotice } from "../components/ErrorNotice";
import form from "../components/form.module.css";
import { KEY_RULE, isValidKey, keyFromName } from "../flags/keys";
import { useCreateFlag } from "../flags/mutations";
import { KIND_LABELS, type VariantDraft, parseVariants, startingVariants } from "../flags/variants";
import { VariantsEditor } from "../flags/VariantsEditor";
import { useApiClient } from "../session/session-context";
import styles from "./page.module.css";

const KINDS: FlagKind[] = ["boolean", "string", "number", "json"];

export function NewFlagPage() {
  const { projectKey = "" } = useParams();
  const project = useQuery(projectQuery(useApiClient(), projectKey));
  const create = useCreateFlag(projectKey);
  const navigate = useNavigate();
  const id = useId();

  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  // The key follows the name until it is edited by hand.
  const [keyEdited, setKeyEdited] = useState(false);
  const [description, setDescription] = useState("");
  const [kind, setKind] = useState<FlagKind>("boolean");
  const [variants, setVariants] = useState<VariantDraft[]>(startingVariants("boolean"));
  const [offVariant, setOffVariant] = useState("off");
  const [onVariant, setOnVariant] = useState("on");
  const [submitted, setSubmitted] = useState(false);
  // A key the API said another flag already has.
  const [takenKey, setTakenKey] = useState<string | null>(null);

  const flagKey = keyEdited ? key : keyFromName(name);
  const parsedVariants = parseVariants(kind, variants);
  const variantKeys = [...new Set(variants.map((variant) => variant.key).filter(isValidKey))];
  const errors = {
    name: name.trim() === "" ? "Give the flag a name." : undefined,
    key: flagKey === takenKey ? "Another flag in this project has this key." : keyProblem(flagKey),
    off: variantKeys.includes(offVariant) ? undefined : "Choose the variant to serve when off.",
    on: variantKeys.includes(onVariant) ? undefined : "Choose the variant to serve when on.",
  };
  const shown = (error: string | undefined) => (submitted ? error : undefined);
  const projectPath = `/projects/${encodeURIComponent(projectKey)}`;

  const chooseKind = (next: FlagKind) => {
    const starting = startingVariants(next);
    setKind(next);
    setVariants(starting);
    setOffVariant(starting[1]?.key ?? "");
    setOnVariant(starting[0]?.key ?? "");
  };

  return (
    <>
      <nav aria-label="Breadcrumb" className={styles.breadcrumb}>
        <ol>
          <li>
            <Link to="/">Projects</Link>
          </li>
          <li>
            <Link to={projectPath}>{project.data?.name ?? projectKey}</Link>
          </li>
          <li aria-current="page">New flag</li>
        </ol>
      </nav>
      <div className={styles.heading}>
        <h1>New flag</h1>
        <p className={styles.subtitle}>
          It starts off in every environment, serving its off variant until you turn it on.
        </p>
      </div>

      <form
        className={form.form}
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          setSubmitted(true);
          const valid =
            parsedVariants.ok && Object.values(errors).every((error) => error === undefined);
          if (!valid) {
            return;
          }
          create.mutate(
            {
              key: flagKey,
              name: name.trim(),
              description: description.trim(),
              kind,
              variants: parsedVariants.value,
              off_variant: offVariant,
              on_variant: onVariant,
            },
            {
              onSuccess: (flag) => {
                void navigate(`${projectPath}/flags/${encodeURIComponent(flag.key)}`);
              },
              onError: (error) => {
                if (hasCode(error, "flag_key_taken")) {
                  setTakenKey(flagKey);
                }
              },
            },
          );
        }}
      >
        <TextField
          id={`${id}-name`}
          label="Name"
          value={name}
          error={shown(errors.name)}
          onChange={setName}
        />
        <TextField
          id={`${id}-key`}
          label="Key"
          hint="What code asks for. It can't be changed once the flag exists."
          mono
          value={flagKey}
          error={shown(errors.key)}
          onChange={(value) => {
            setKeyEdited(true);
            setKey(value);
          }}
        />
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

        <fieldset className={form.fieldset}>
          <legend className={form.legend}>Kind</legend>
          <div className={form.choices}>
            {KINDS.map((option) => (
              <label key={option} className={form.choice}>
                <input
                  type="radio"
                  name={`${id}-kind`}
                  value={option}
                  checked={kind === option}
                  onChange={() => {
                    chooseKind(option);
                  }}
                />
                {KIND_LABELS[option]}
              </label>
            ))}
          </div>
        </fieldset>

        <VariantsEditor
          kind={kind}
          variants={variants}
          errors={submitted && !parsedVariants.ok ? parsedVariants.errors : null}
          onChange={setVariants}
        />

        <div className={form.row}>
          <VariantSelect
            id={`${id}-off`}
            label="Served when off"
            options={variantKeys}
            value={offVariant}
            error={shown(errors.off)}
            onChange={setOffVariant}
          />
          <VariantSelect
            id={`${id}-on`}
            label="Served when turned on"
            options={variantKeys}
            value={onVariant}
            error={shown(errors.on)}
            onChange={setOnVariant}
          />
        </div>

        {create.isError && !hasCode(create.error, "flag_key_taken") && (
          <ErrorNotice error={create.error} />
        )}
        <div className={form.actions}>
          <Button type="submit" variant="primary" disabled={create.isPending}>
            {create.isPending ? "Creating flag…" : "Create flag"}
          </Button>
          <Link to={projectPath}>Cancel</Link>
        </div>
      </form>
    </>
  );
}

function keyProblem(key: string): string | undefined {
  if (key === "") {
    return "Give the flag a key.";
  }
  return isValidKey(key) ? undefined : KEY_RULE;
}

interface TextFieldProps {
  id: string;
  label: string;
  hint?: string;
  mono?: boolean;
  value: string;
  error: string | undefined;
  onChange: (value: string) => void;
}

function TextField({ id, label, hint, mono = false, value, error, onChange }: TextFieldProps) {
  const described = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(" ");
  return (
    <div className={form.field}>
      <label htmlFor={id} className={form.label}>
        {label}
      </label>
      <input
        id={id}
        className={cx(form.input, mono && form.mono)}
        value={value}
        spellCheck={!mono}
        autoComplete="off"
        aria-invalid={error !== undefined}
        aria-describedby={described || undefined}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      {hint !== undefined && (
        <p id={`${id}-hint`} className={form.hint}>
          {hint}
        </p>
      )}
      {error !== undefined && (
        <p id={`${id}-error`} className={form.error}>
          {error}
        </p>
      )}
    </div>
  );
}

interface VariantSelectProps {
  id: string;
  label: string;
  options: string[];
  value: string;
  error: string | undefined;
  onChange: (value: string) => void;
}

function VariantSelect({ id, label, options, value, error, onChange }: VariantSelectProps) {
  return (
    <div className={form.field}>
      <label htmlFor={id} className={form.label}>
        {label}
      </label>
      <select
        id={id}
        className={cx(form.input, form.mono)}
        value={options.includes(value) ? value : ""}
        aria-invalid={error !== undefined}
        aria-describedby={error === undefined ? undefined : `${id}-error`}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      >
        <option value="" disabled>
          Choose a variant
        </option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      {error !== undefined && (
        <p id={`${id}-error`} className={form.error}>
          {error}
        </p>
      )}
    </div>
  );
}
