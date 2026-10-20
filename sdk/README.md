# flagstaff

Python SDK for [Flagstaff](https://github.com/emilbogdanov/feature-flag-service) feature flags.
It keeps one environment's rules in memory and evaluates flags in-process, so checking a flag
never waits on the network. The server pushes every change over server-sent events, and the SDK
swaps the new rules in as they arrive.

```
pip install "flagstaff @ git+https://github.com/emilbogdanov/feature-flag-service@v0.1.0#subdirectory=sdk"
```

Python 3.12 or newer. The only dependency is httpx.

## Reading flags

Every getter takes a default. Whenever the SDK can't give a real answer (no rules yet, an unknown
flag, a flag of a different type), it returns that default instead of raising, so a flag check
can't take a request down.

```python
from flagstaff import EvaluationContext, FlagstaffClient

flags = FlagstaffClient("fs_sdk_...", base_url="https://flags.example.com")
flags.wait_until_ready(timeout=5)

flags.bool_value("new-checkout", "user-7", default=False)
# True

shopper = EvaluationContext("user-310", {"country": "DE", "plan": "pro"})
flags.bool_detail("new-checkout", shopper, default=False)
# FlagDetail(value=False, variant='off', reason=<Reason.RULE_MATCH: 'rule_match'>,
#            rule_id='eu-pro', ruleset_version=4)

flags.str_detail("checkout-theme", "user-7", default="classic")
# FlagDetail(value='classic', variant=None, reason=<Reason.FLAG_NOT_FOUND: 'flag_not_found'>,
#            rule_id=None, ruleset_version=4)
```

The context is a user key, or an `EvaluationContext` with the attributes that targeting rules
match on: strings, numbers and booleans. There are `bool_`, `str_`, `number_` and `json_` getters,
each in a `_value` and a `_detail` form. `json_value` returns a copy, so changing it can't change
the rules.

`FlagDetail.reason` says why the value is what it is:

| Reason | Value |
| --- | --- |
| `disabled` | the flag is switched off in this environment and serves its off variant |
| `rule_match` | a targeting rule matched; `rule_id` names it |
| `fallthrough` | no rule matched |
| `not_ready` | your default: no rules have arrived yet |
| `flag_not_found` | your default: the environment has no flag with that key |
| `wrong_type` | your default: the flag is of another kind than the getter asked for |
| `invalid_context` | your default: the user key given as a string was empty |

Apart from `not_ready`, each fallback is also logged as a warning on the `flagstaff` logger, once
per flag and reason, so a hot code path asking for a missing flag doesn't flood the log.

## Keeping rules current

`FlagstaffClient` updates on a background thread with its own event loop, for Django, Flask,
Celery workers and scripts. `AsyncFlagstaffClient` runs the same updates as a task on your event
loop, for FastAPI and other asyncio apps:

```python
from flagstaff import AsyncFlagstaffClient

async with AsyncFlagstaffClient("fs_sdk_...", base_url="https://flags.example.com") as flags:
    await flags.wait_until_ready(timeout=5)
    flags.bool_value("new-checkout", "user-7", default=False)
```

Both take the same keyword arguments:

| Argument | Default | |
| --- | --- | --- |
| `base_url` | required | where the Flagstaff API answers |
| `streaming` | `True` | follow `/sdk/stream`; `False` polls `/sdk/ruleset` instead |
| `poll_interval` | `60.0` | seconds between polls, when not streaming |
| `cache_path` | `None` | a file to keep the last rules in, for starting while the server is down |
| `connect_timeout` | `5.0` | seconds |
| `read_timeout` | `45.0` | seconds without a byte, keep-alives included, before reconnecting |
| `initial_reconnect_delay` | `0.5` | the first wait after a dropped connection, in seconds |
| `max_reconnect_delay` | `30.0` | the longest wait between attempts, in seconds |

When the server can't be reached, the SDK keeps serving the rules it has and reconnects with
exponential backoff and full jitter, so a fleet of apps doesn't come back in lockstep. It never
goes back to an older version than the one it holds. A key the server rejects with 401 or 403
stops the updates for good and logs an error, since retrying can't fix it.

With `cache_path`, every new ruleset is written to that file, through a temporary file renamed
into place. A process that starts while the server is down begins from those rules instead of
every default in the code.

## Processes that fork

Create clients after forking. A client made in a gunicorn master with `--preload`, for example,
leaves its update thread behind in the master, and the workers would never get new rules.

## License

Released under the [MIT License](https://github.com/emilbogdanov/feature-flag-service/blob/main/sdk/LICENSE).
Copyright © 2026 Emil Bogdanov.
