import { describeError } from "../api/errors";
import type { EnvironmentResponse, FlagResponse } from "../api/schema";
import styles from "./FlagSwitch.module.css";
import { useSwitchFlag } from "./mutations";

interface FlagSwitchProps {
  projectKey: string;
  flag: FlagResponse;
  environment: EnvironmentResponse;
  // Called with null when a switch starts, and with what went wrong when it fails.
  onFailure: (message: string | null) => void;
}

export function FlagSwitch({ projectKey, flag, environment, onFailure }: FlagSwitchProps) {
  const switchFlag = useSwitchFlag(projectKey);
  const on = flag.environments[environment.key]?.enabled ?? false;
  const action = on ? "turn off" : "turn on";

  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={`${flag.name} in ${environment.name}`}
      className={styles.switch}
      disabled={switchFlag.isPending}
      onClick={() => {
        onFailure(null);
        switchFlag.mutate(
          { flag, environmentKey: environment.key, on: !on },
          {
            onError: (error) => {
              onFailure(
                `Couldn't ${action} ${flag.name} in ${environment.name}. ${describeError(error)}`,
              );
            },
          },
        );
      }}
    >
      <span className={styles.track} aria-hidden="true" />
      <span className={styles.state}>{on ? "On" : "Off"}</span>
    </button>
  );
}
