import { useId, useState } from "react";

import { isConflict } from "../api/errors";
import type { EnvironmentResponse, FlagResponse } from "../api/schema";
import { Button } from "../components/Button";
import { cx } from "../components/cx";
import { ErrorNotice } from "../components/ErrorNotice";
import form from "../components/form.module.css";
import page from "../pages/page.module.css";
import { useChangeTargeting } from "./mutations";
import { RuleEditor } from "./RuleEditor";
import { ServeEditor } from "./ServeEditor";
import { type TargetingDraft, newRule, parseTargeting, targetingDraft } from "./targeting";
import styles from "./TargetingEditor.module.css";

interface TargetingFormProps {
  projectKey: string;
  flag: FlagResponse;
  environment: EnvironmentResponse;
}

interface Edit {
  draft: TargetingDraft;
  // The flag version the draft started from. Saving names it, so a change someone else made in
  // the meantime is not overwritten.
  version: number;
}

function startEdit(flag: FlagResponse, environmentKey: string): Edit | null {
  const targeting = flag.environments[environmentKey];
  return targeting === undefined
    ? null
    : { draft: targetingDraft(targeting, flag.variants), version: flag.version };
}

export function TargetingForm({ projectKey, flag, environment }: TargetingFormProps) {
  const save = useChangeTargeting(projectKey);
  const id = useId();
  const [edit, setEdit] = useState(() => startEdit(flag, environment.key));
  const [submitted, setSubmitted] = useState(false);
  const [saved, setSaved] = useState(false);

  if (edit === null) {
    return <p>This flag has no targeting for {environment.name} yet.</p>;
  }
  const { draft, version } = edit;
  const parsed = parseTargeting(draft, flag.variants);
  const errorOf = (path: string) => (submitted && !parsed.ok ? parsed.errors.get(path) : undefined);
  // The flag on screen is refreshed from the API; a newer version that isn't this form's own save
  // means someone else changed it.
  const changedElsewhere =
    flag.version !== version && save.data?.version !== flag.version && !save.isPending;

  const update = (change: (next: TargetingDraft) => void) => {
    const next = structuredClone(draft);
    change(next);
    setEdit({ draft: next, version });
    setSaved(false);
  };
  const reload = () => {
    setEdit(startEdit(flag, environment.key));
    setSubmitted(false);
    save.reset();
  };

  return (
    <form
      className={form.form}
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        setSubmitted(true);
        if (!parsed.ok) {
          return;
        }
        save.mutate(
          { flagKey: flag.key, version, environmentKey: environment.key, targeting: parsed.value },
          {
            onSuccess: (changed) => {
              setEdit(startEdit(changed, environment.key));
              setSubmitted(false);
              setSaved(true);
            },
          },
        );
      }}
    >
      {(changedElsewhere || isConflict(save.error)) && (
        <div className={page.notice} role="status">
          <p>
            The flag changed after you started editing. Saving now would be refused; load the latest
            version to see what changed, then make your edit again.
          </p>
          <Button onClick={reload}>Discard my changes and load the latest</Button>
        </div>
      )}

      <label className={styles.state}>
        <input
          type="checkbox"
          checked={draft.enabled}
          onChange={(event) => {
            update((next) => {
              next.enabled = event.target.checked;
            });
          }}
        />
        On in {environment.name}
      </label>
      <p className={form.hint}>
        While on, users get the first rule they match, or the variant for everyone else. While off,
        everyone gets the off variant.
      </p>

      <div className={form.field}>
        <label htmlFor={`${id}-off`} className={form.label}>
          Served while off
        </label>
        <select
          id={`${id}-off`}
          className={cx(form.input, form.mono)}
          value={draft.offVariant}
          aria-invalid={errorOf("offVariant") !== undefined}
          aria-describedby={errorOf("offVariant") === undefined ? undefined : `${id}-off-error`}
          onChange={(event) => {
            update((next) => {
              next.offVariant = event.target.value;
            });
          }}
        >
          {flag.variants.map((variant) => (
            <option key={variant.key} value={variant.key}>
              {variant.key}
            </option>
          ))}
        </select>
        {errorOf("offVariant") !== undefined && (
          <p id={`${id}-off-error`} className={form.error}>
            {errorOf("offVariant")}
          </p>
        )}
      </div>

      <section className={page.section} aria-labelledby={`${id}-rules`}>
        <h2 id={`${id}-rules`}>Rules</h2>
        {draft.rules.length === 0 ? (
          <p className={page.muted}>No rules: everyone gets the variant below.</p>
        ) : (
          <ol className={styles.rules}>
            {draft.rules.map((rule, index) => (
              <li key={rule.uid}>
                <RuleEditor
                  rule={rule}
                  position={index + 1}
                  count={draft.rules.length}
                  variants={flag.variants}
                  errorOf={(path) => errorOf(`rules.${String(index)}.${path}`)}
                  onChange={(changed) => {
                    update((next) => {
                      next.rules[index] = changed;
                    });
                  }}
                  onMove={(offset) => {
                    update((next) => {
                      const [moved] = next.rules.splice(index, 1);
                      if (moved !== undefined) {
                        next.rules.splice(index + offset, 0, moved);
                      }
                    });
                  }}
                  onRemove={() => {
                    update((next) => {
                      next.rules.splice(index, 1);
                    });
                  }}
                />
              </li>
            ))}
          </ol>
        )}
        <div>
          <Button
            onClick={() => {
              update((next) => {
                next.rules.push(newRule(next.rules, flag.variants));
              });
            }}
          >
            Add rule
          </Button>
        </div>
      </section>

      <ServeEditor
        legend="Everyone else"
        serve={draft.fallthrough}
        variants={flag.variants}
        error={errorOf("fallthrough")}
        onChange={(serve) => {
          update((next) => {
            next.fallthrough = serve;
          });
        }}
      />

      {submitted && !parsed.ok && (
        <p className={form.error} role="alert">
          Some fields need fixing before this can be saved.
        </p>
      )}
      {/* A save refused over someone else's change is explained at the top instead. */}
      {save.isError && !isConflict(save.error) && <ErrorNotice error={save.error} />}
      {saved && (
        <p role="status" className={page.muted}>
          Saved. SDKs connected to {environment.name} are getting the new rules now.
        </p>
      )}
      <div className={form.actions}>
        <Button type="submit" variant="primary" disabled={save.isPending}>
          {save.isPending ? "Saving…" : `Save targeting for ${environment.name}`}
        </Button>
        <Button onClick={reload}>Discard changes</Button>
      </div>
    </form>
  );
}
