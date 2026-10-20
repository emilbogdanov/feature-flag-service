import { useId } from "react";

import type { FlagKind } from "../api/schema";
import { Button } from "../components/Button";
import { cx } from "../components/cx";
import form from "../components/form.module.css";
import styles from "./VariantsEditor.module.css";
import type { VariantDraft, VariantErrors } from "./variants";

interface VariantsEditorProps {
  kind: FlagKind;
  variants: VariantDraft[];
  // One entry per variant, shown only once the form has been sent.
  errors: VariantErrors[] | null;
  onChange: (variants: VariantDraft[]) => void;
}

export function VariantsEditor({ kind, variants, errors, onChange }: VariantsEditorProps) {
  const id = useId();
  const change = (index: number, changed: Partial<VariantDraft>) => {
    onChange(variants.map((variant, at) => (at === index ? { ...variant, ...changed } : variant)));
  };

  return (
    <fieldset className={form.fieldset}>
      <legend className={form.legend}>Variants</legend>
      <p className={form.hint}>
        The values the flag can serve. Code asks for a variant&apos;s value.
      </p>
      <ol className={styles.list}>
        {variants.map((variant, index) => {
          const keyId = `${id}-key-${String(index)}`;
          const valueId = `${id}-value-${String(index)}`;
          const keyError = errors?.[index]?.key;
          const valueError = errors?.[index]?.value;
          const number = String(index + 1);
          return (
            <li key={index} className={styles.variant}>
              <div className={form.field}>
                <label htmlFor={keyId} className={form.hint}>
                  Key of variant {number}
                </label>
                <input
                  id={keyId}
                  className={cx(form.input, form.mono)}
                  value={variant.key}
                  spellCheck={false}
                  autoComplete="off"
                  aria-invalid={keyError !== undefined}
                  aria-describedby={keyError === undefined ? undefined : `${keyId}-error`}
                  onChange={(event) => {
                    change(index, { key: event.target.value });
                  }}
                />
                {keyError !== undefined && (
                  <p id={`${keyId}-error`} className={form.error}>
                    {keyError}
                  </p>
                )}
              </div>
              <div className={cx(form.field, styles.value)}>
                <label htmlFor={valueId} className={form.hint}>
                  Value of variant {number}
                </label>
                <ValueInput
                  id={valueId}
                  kind={kind}
                  value={variant.value}
                  error={valueError}
                  onChange={(value) => {
                    change(index, { value });
                  }}
                />
                {valueError !== undefined && (
                  <p id={`${valueId}-error`} className={form.error}>
                    {valueError}
                  </p>
                )}
              </div>
              {variants.length > 1 && (
                <Button
                  className={styles.remove}
                  aria-label={`Remove variant ${number}`}
                  onClick={() => {
                    onChange(variants.filter((_, at) => at !== index));
                  }}
                >
                  Remove
                </Button>
              )}
            </li>
          );
        })}
      </ol>
      <Button
        className={styles.add}
        onClick={() => {
          onChange([...variants, { key: "", value: kind === "boolean" ? "true" : "" }]);
        }}
      >
        Add variant
      </Button>
    </fieldset>
  );
}

interface ValueInputProps {
  id: string;
  kind: FlagKind;
  value: string;
  error: string | undefined;
  onChange: (value: string) => void;
}

function ValueInput({ id, kind, value, error, onChange }: ValueInputProps) {
  const shared = {
    id,
    value,
    "aria-invalid": error !== undefined,
    "aria-describedby": error === undefined ? undefined : `${id}-error`,
  };
  switch (kind) {
    case "boolean":
      return (
        <select
          {...shared}
          className={form.input}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        >
          <option value="true">true</option>
          <option value="false">false</option>
        </select>
      );
    case "json":
      return (
        <textarea
          {...shared}
          className={cx(form.input, form.mono)}
          spellCheck={false}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
      );
    case "number":
    case "string":
      return (
        <input
          {...shared}
          className={form.input}
          inputMode={kind === "number" ? "decimal" : undefined}
          autoComplete="off"
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
      );
  }
}
