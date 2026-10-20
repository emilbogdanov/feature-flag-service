import type { FixedServeSchema, RolloutServeSchema } from "../api/schema";

export type Serve = FixedServeSchema | RolloutServeSchema;

// Rollout weights are out of 100,000, so a share can be as fine as a thousandth of a percent.
export const WEIGHT_TOTAL = 100_000;
const WEIGHT_PER_PERCENT = WEIGHT_TOTAL / 100;

export function isRollout(serve: Serve): serve is RolloutServeSchema {
  return "rollout" in serve;
}

// Not locale-formatted: percentages are typed back into inputs, which take a dot.
export function formatPercent(weight: number): string {
  return `${String(Number((weight / WEIGHT_PER_PERCENT).toFixed(3)))}%`;
}

// "on" for a fixed variant, "on 20%, off 80%" for a rollout.
export function describeServe(serve: Serve): string {
  if (!isRollout(serve)) {
    return serve.variant;
  }
  return serve.rollout.map((share) => `${share.variant} ${formatPercent(share.weight)}`).join(", ");
}
