import { useId } from "react";

import type { VariantSchema } from "../api/schema";
import { Button } from "../components/Button";
import { cx } from "../components/cx";
import form from "../components/form.module.css";
import { ConditionEditor } from "./ConditionEditor";
import { ServeEditor } from "./ServeEditor";
import { type RuleDraft, newCondition, newUserList } from "./targeting";
import styles from "./TargetingEditor.module.css";

interface RuleEditorProps {
  rule: RuleDraft;
  position: number;
  count: number;
  variants: VariantSchema[];
  // Errors for this rule, by the path below it, such as "conditions.0.values".
  errorOf: (path: string) => string | undefined;
  onChange: (rule: RuleDraft) => void;
  onMove: (offset: -1 | 1) => void;
  onRemove: () => void;
}

export function RuleEditor({
  rule,
  position,
  count,
  variants,
  errorOf,
  onChange,
  onMove,
  onRemove,
}: RuleEditorProps) {
  const id = useId();
  const title = `Rule ${String(position)}`;
  const idError = errorOf("id");
  const conditionsError = errorOf("conditions");

  return (
    <fieldset className={styles.rule}>
      <legend className="visually-hidden">{title}</legend>
      <div className={styles.ruleHeader}>
        <span className={styles.ruleTitle} aria-hidden="true">
          {title}
        </span>
        <div className={styles.toolbar}>
          <Button
            disabled={position === 1}
            onClick={() => {
              onMove(-1);
            }}
          >
            Move up
          </Button>
          <Button
            disabled={position === count}
            onClick={() => {
              onMove(1);
            }}
          >
            Move down
          </Button>
          <Button onClick={onRemove}>Remove rule</Button>
        </div>
      </div>

      <div className={styles.ruleId}>
        <label htmlFor={`${id}-id`} className={form.hint}>
          Rule id, reported with each evaluation it decides
        </label>
        <input
          id={`${id}-id`}
          className={cx(form.input, form.mono)}
          value={rule.id}
          spellCheck={false}
          autoComplete="off"
          aria-invalid={idError !== undefined}
          aria-describedby={idError === undefined ? undefined : `${id}-id-error`}
          onChange={(event) => {
            onChange({ ...rule, id: event.target.value });
          }}
        />
        {idError !== undefined && (
          <p id={`${id}-id-error`} className={form.error}>
            {idError}
          </p>
        )}
      </div>

      <div className={form.fieldset}>
        <p className={form.legend}>Applies to users for whom all of these hold</p>
        <ol className={styles.conditions}>
          {rule.conditions.map((condition, index) => (
            <li key={condition.uid}>
              <ConditionEditor
                legend={`Condition ${String(index + 1)} of ${title.toLowerCase()}`}
                condition={condition}
                errorOf={(field) => errorOf(`conditions.${String(index)}.${field}`)}
                onChange={(changed) => {
                  onChange({
                    ...rule,
                    conditions: rule.conditions.map((other, at) =>
                      at === index ? changed : other,
                    ),
                  });
                }}
                onRemove={() => {
                  onChange({
                    ...rule,
                    conditions: rule.conditions.filter((_, at) => at !== index),
                  });
                }}
              />
            </li>
          ))}
        </ol>
        {conditionsError !== undefined && <p className={form.error}>{conditionsError}</p>}
        <div className={styles.toolbar}>
          <Button
            onClick={() => {
              onChange({ ...rule, conditions: [...rule.conditions, newCondition()] });
            }}
          >
            Add attribute condition
          </Button>
          <Button
            onClick={() => {
              onChange({ ...rule, conditions: [...rule.conditions, newUserList()] });
            }}
          >
            Add user list
          </Button>
        </div>
      </div>

      <ServeEditor
        legend="Serve"
        serve={rule.serve}
        variants={variants}
        error={errorOf("serve")}
        onChange={(serve) => {
          onChange({ ...rule, serve });
        }}
      />
    </fieldset>
  );
}
