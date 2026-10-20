import { useId } from "react";

import type { VariantSchema } from "../api/schema";
import { cx } from "../components/cx";
import form from "../components/form.module.css";
import { WEIGHT_TOTAL, formatPercent } from "./serve";
import type { ServeDraft } from "./targeting";
import styles from "./TargetingEditor.module.css";

interface ServeEditorProps {
  legend: string;
  serve: ServeDraft;
  variants: VariantSchema[];
  error: string | undefined;
  onChange: (serve: ServeDraft) => void;
}

export function ServeEditor({ legend, serve, variants, error, onChange }: ServeEditorProps) {
  const id = useId();
  const errorId = `${id}-error`;
  const described = error === undefined ? undefined : errorId;

  return (
    <fieldset className={form.fieldset}>
      <legend className={form.legend}>{legend}</legend>
      <div className={form.choices}>
        <label className={form.choice}>
          <input
            type="radio"
            name={`${id}-mode`}
            checked={serve.mode === "fixed"}
            onChange={() => {
              onChange({ ...serve, mode: "fixed" });
            }}
          />
          One variant
        </label>
        <label className={form.choice}>
          <input
            type="radio"
            name={`${id}-mode`}
            checked={serve.mode === "rollout"}
            onChange={() => {
              onChange({ ...serve, mode: "rollout" });
            }}
          />
          A percentage of users each
        </label>
      </div>

      {serve.mode === "fixed" ? (
        <div className={form.field}>
          <label htmlFor={`${id}-variant`} className={form.hint}>
            Variant
          </label>
          <select
            id={`${id}-variant`}
            className={cx(form.input, form.mono)}
            value={variants.some((variant) => variant.key === serve.variant) ? serve.variant : ""}
            aria-invalid={error !== undefined}
            aria-describedby={described}
            onChange={(event) => {
              onChange({ ...serve, variant: event.target.value });
            }}
          >
            <option value="" disabled>
              Choose a variant
            </option>
            {variants.map((variant) => (
              <option key={variant.key} value={variant.key}>
                {variant.key}
              </option>
            ))}
          </select>
        </div>
      ) : (
        <>
          <p className={form.hint}>
            Each user lands in the same place every time, so raising one share moves users into it
            from the shares next to it and nobody else.
          </p>
          <ol className={styles.shares}>
            {serve.shares.map((share, index) => {
              const inputId = `${id}-share-${String(index)}`;
              return (
                <li key={share.variant} className={styles.share}>
                  <label htmlFor={inputId}>
                    <code>{share.variant}</code>
                  </label>
                  <input
                    id={inputId}
                    className={cx(form.input, styles.percent)}
                    inputMode="decimal"
                    autoComplete="off"
                    value={share.percent}
                    aria-invalid={error !== undefined}
                    aria-describedby={described}
                    onChange={(event) => {
                      onChange({
                        ...serve,
                        shares: serve.shares.map((other, at) =>
                          at === index ? { ...other, percent: event.target.value } : other,
                        ),
                      });
                    }}
                  />
                  <span aria-hidden="true">%</span>
                </li>
              );
            })}
          </ol>
          <p className={cx(form.hint, styles.total)}>Total: {totalOf(serve)}</p>
        </>
      )}
      {error !== undefined && (
        <p id={errorId} className={form.error}>
          {error}
        </p>
      )}
    </fieldset>
  );
}

// The running total while shares are typed, from whatever parses as a number.
function totalOf(serve: ServeDraft): string {
  const weight = serve.shares.reduce((sum, share) => {
    const percent = Number(share.percent.trim() === "" ? "0" : share.percent);
    return Number.isFinite(percent) ? sum + Math.round(percent * (WEIGHT_TOTAL / 100)) : sum;
  }, 0);
  return formatPercent(weight);
}
