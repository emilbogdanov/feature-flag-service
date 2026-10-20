import { type ReactNode, useId } from "react";

import type { Operator } from "../api/schema";
import { Button } from "../components/Button";
import { cx } from "../components/cx";
import form from "../components/form.module.css";
import {
  type ConditionDraft,
  OPERATOR_LABELS,
  type ValueKind,
  takesOneNumber,
  takesText,
} from "./targeting";
import styles from "./TargetingEditor.module.css";

const OPERATORS = Object.keys(OPERATOR_LABELS) as Operator[];
const VALUE_KINDS: Record<ValueKind, string> = {
  text: "Text",
  number: "Numbers",
  boolean: "True or false",
};

interface ConditionEditorProps {
  legend: string;
  condition: ConditionDraft;
  // Errors for this condition, by field name.
  errorOf: (field: string) => string | undefined;
  onChange: (condition: ConditionDraft) => void;
  onRemove: () => void;
}

export function ConditionEditor({
  legend,
  condition,
  errorOf,
  onChange,
  onRemove,
}: ConditionEditorProps) {
  const id = useId();
  const remove = (
    <Button className={styles.lowered} onClick={onRemove}>
      Remove condition
    </Button>
  );

  if (condition.type === "user_list") {
    const error = errorOf("userKeys");
    return (
      <fieldset className={cx(styles.condition, styles.userList)}>
        <legend className="visually-hidden">{legend}</legend>
        <Field id={`${id}-users`} label="User keys, one per line" error={error}>
          <textarea
            id={`${id}-users`}
            className={cx(form.input, form.mono)}
            value={condition.userKeys}
            spellCheck={false}
            aria-invalid={error !== undefined}
            aria-describedby={error === undefined ? undefined : `${id}-users-error`}
            onChange={(event) => {
              onChange({ ...condition, userKeys: event.target.value });
            }}
          />
        </Field>
        {remove}
      </fieldset>
    );
  }

  const attributeError = errorOf("attribute");
  const valuesError = errorOf("values");
  const oneNumber = takesOneNumber(condition.operator);
  const valuesProps = {
    id: `${id}-values`,
    value: condition.values,
    "aria-invalid": valuesError !== undefined,
    "aria-describedby": valuesError === undefined ? undefined : `${id}-values-error`,
  };

  return (
    <fieldset className={styles.condition}>
      <legend className="visually-hidden">{legend}</legend>
      <Field id={`${id}-attribute`} label="Attribute" error={attributeError}>
        <input
          id={`${id}-attribute`}
          className={cx(form.input, form.mono)}
          value={condition.attribute}
          spellCheck={false}
          autoComplete="off"
          aria-invalid={attributeError !== undefined}
          aria-describedby={attributeError === undefined ? undefined : `${id}-attribute-error`}
          onChange={(event) => {
            onChange({ ...condition, attribute: event.target.value });
          }}
        />
      </Field>
      <label className={styles.negate}>
        <input
          type="checkbox"
          checked={condition.negate}
          onChange={(event) => {
            onChange({ ...condition, negate: event.target.checked });
          }}
        />
        not
      </label>
      <Field id={`${id}-operator`} label="Comparison">
        <select
          id={`${id}-operator`}
          className={form.input}
          value={condition.operator}
          onChange={(event) => {
            onChange({ ...condition, operator: event.target.value as Operator });
          }}
        >
          {OPERATORS.map((operator) => (
            <option key={operator} value={operator}>
              {OPERATOR_LABELS[operator]}
            </option>
          ))}
        </select>
      </Field>
      <div className={form.field}>
        {oneNumber ? (
          <Field id={`${id}-values`} label="Number" error={valuesError}>
            <input
              {...valuesProps}
              className={form.input}
              inputMode="decimal"
              autoComplete="off"
              onChange={(event) => {
                onChange({ ...condition, values: event.target.value });
              }}
            />
          </Field>
        ) : (
          <Field id={`${id}-values`} label="Values, one per line" error={valuesError}>
            <textarea
              {...valuesProps}
              className={cx(form.input, form.mono)}
              spellCheck={false}
              onChange={(event) => {
                onChange({ ...condition, values: event.target.value });
              }}
            />
          </Field>
        )}
        {condition.operator === "in" && (
          <Field id={`${id}-kind`} label="Values are">
            <select
              id={`${id}-kind`}
              className={form.input}
              value={condition.valueKind}
              onChange={(event) => {
                onChange({ ...condition, valueKind: event.target.value as ValueKind });
              }}
            >
              {(Object.keys(VALUE_KINDS) as ValueKind[]).map((kind) => (
                <option key={kind} value={kind}>
                  {VALUE_KINDS[kind]}
                </option>
              ))}
            </select>
          </Field>
        )}
        {takesText(condition.operator) && <p className={form.hint}>Compared as text.</p>}
      </div>
      {remove}
    </fieldset>
  );
}

interface FieldProps {
  id: string;
  label: string;
  error?: string | undefined;
  children: ReactNode;
}

function Field({ id, label, error, children }: FieldProps) {
  return (
    <div className={form.field}>
      <label htmlFor={id} className={form.hint}>
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
