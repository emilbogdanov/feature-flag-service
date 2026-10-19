from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from uuid import uuid4

if TYPE_CHECKING:
    from httpx import AsyncClient

ENVIRONMENT: Final = "prod"
# The flag the load test evaluates and flips. Its rules make evaluation do real work: a user
# list, then an attribute match served by a percentage rollout.
FLAG: Final = "load-checkout"
_TARGETING: Final = {
    "enabled": True,
    "off_variant": "off",
    "rules": [
        {
            "id": "testers",
            "conditions": [{"type": "user_list", "user_keys": ["user-7", "user-1042"]}],
            "serve": {"variant": "on"},
        },
        {
            "id": "eu-pro",
            "conditions": [
                {
                    "type": "attribute",
                    "attribute": "country",
                    "operator": "in",
                    "values": ["BG", "DE", "FR"],
                    "negate": False,
                },
                {
                    "type": "attribute",
                    "attribute": "plan",
                    "operator": "in",
                    "values": ["pro"],
                    "negate": False,
                },
            ],
            "serve": {
                "rollout": [
                    {"variant": "on", "weight": 25_000},
                    {"variant": "off", "weight": 75_000},
                ]
            },
        },
    ],
    "fallthrough": {"variant": "off"},
}


@dataclass(frozen=True, slots=True)
class Target:
    project: str
    flag_count: int
    sdk_key: str


# A project of its own on every run, so runs against the same stack never see each other's
# flags. The other flags only give the ruleset a realistic size.
async def prepare(admin: AsyncClient, *, flag_count: int) -> Target:
    project = f"load-{uuid4().hex[:8]}"
    await _send(admin, "POST", "/projects", {"key": project, "name": "Load test"})
    flags = f"/projects/{project}/flags"
    for key in [FLAG, *(f"load-filler-{n:02d}" for n in range(1, flag_count))]:
        await _send(admin, "POST", flags, _boolean_flag(key))
        await _send(admin, "POST", f"{flags}/{key}/environments/{ENVIRONMENT}/enable")
    await _send(
        admin,
        "PUT",
        f"{flags}/{FLAG}/environments/{ENVIRONMENT}/targeting",
        _TARGETING,
        headers={"If-Match": "*"},
    )
    issued = await _send(
        admin,
        "POST",
        "/api-keys",
        {"kind": "sdk", "name": "load test", "project": project, "environment": ENVIRONMENT},
    )
    return Target(project=project, flag_count=flag_count, sdk_key=str(issued["secret"]))


async def switch(admin: AsyncClient, target: Target, *, on: bool) -> None:
    action = "enable" if on else "disable"
    await _send(
        admin,
        "POST",
        f"/projects/{target.project}/flags/{FLAG}/environments/{ENVIRONMENT}/{action}",
    )


def _boolean_flag(key: str) -> dict[str, object]:
    return {
        "key": key,
        "name": key.replace("-", " ").capitalize(),
        "kind": "boolean",
        "variants": [{"key": "on", "value": True}, {"key": "off", "value": False}],
        "off_variant": "off",
        "on_variant": "on",
    }


async def _send(
    admin: AsyncClient,
    method: str,
    path: str,
    body: object = None,
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, object]:
    response = await admin.request(method, path, json=body, headers=headers)
    if response.is_error:
        raise RuntimeError(f"{method} {path} answered {response.status_code}: {response.text}")
    payload: dict[str, object] = response.json()
    return payload
