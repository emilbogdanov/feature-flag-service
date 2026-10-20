import { useState } from "react";

import type { FlagResponse } from "../api/schema";
import { Button } from "../components/Button";
import { ErrorNotice } from "../components/ErrorNotice";
import form from "../components/form.module.css";
import page from "../pages/page.module.css";
import { useChangeVariants } from "./mutations";
import { formatValue, parseVariants, variantDrafts } from "./variants";
import { VariantsEditor } from "./VariantsEditor";

interface VariantsSectionProps {
  projectKey: string;
  flag: FlagResponse;
  editable: boolean;
}

export function VariantsSection({ projectKey, flag, editable }: VariantsSectionProps) {
  const [editing, setEditing] = useState(false);

  return (
    <section className={page.section} aria-labelledby="variants">
      <h2 id="variants">Variants</h2>
      {editing ? (
        <VariantsForm
          projectKey={projectKey}
          flag={flag}
          onDone={() => {
            setEditing(false);
          }}
        />
      ) : (
        <>
          <table>
            <thead>
              <tr>
                <th scope="col">Key</th>
                <th scope="col">Value</th>
              </tr>
            </thead>
            <tbody>
              {flag.variants.map((variant) => (
                <tr key={variant.key}>
                  <td>
                    <code>{variant.key}</code>
                  </td>
                  <td>
                    <code className={page.value}>{formatValue(flag.kind, variant.value)}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {editable && (
            <div>
              <Button
                onClick={() => {
                  setEditing(true);
                }}
              >
                Edit variants
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  );
}

interface VariantsFormProps {
  projectKey: string;
  flag: FlagResponse;
  onDone: () => void;
}

function VariantsForm({ projectKey, flag, onDone }: VariantsFormProps) {
  const change = useChangeVariants(projectKey);
  const [variants, setVariants] = useState(() => variantDrafts(flag.kind, flag.variants));
  const [submitted, setSubmitted] = useState(false);
  const parsed = parseVariants(flag.kind, variants);

  return (
    <form
      className={form.form}
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        setSubmitted(true);
        if (parsed.ok) {
          change.mutate({ flag, variants: parsed.value }, { onSuccess: onDone });
        }
      }}
    >
      <p className={form.hint}>
        A variant some environment still serves can&apos;t be removed; change that targeting first.
      </p>
      <VariantsEditor
        kind={flag.kind}
        variants={variants}
        errors={submitted && !parsed.ok ? parsed.errors : null}
        onChange={setVariants}
      />
      {change.isError && <ErrorNotice error={change.error} />}
      <div className={form.actions}>
        <Button type="submit" variant="primary" disabled={change.isPending}>
          {change.isPending ? "Saving…" : "Save variants"}
        </Button>
        <Button onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}
