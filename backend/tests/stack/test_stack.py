# Drives the stack in compose.yaml from outside, the way a client would: through nginx, with
# both API instances behind it. CI runs these once the stack is up; to run them yourself:
#   docker compose up --build --wait
#   FLAGSTAFF_STACK_URL=http://localhost:8080 uv run pytest tests/stack
import asyncio
import os
import re
import subprocess
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from uuid import uuid4

import pytest
from flagstaff import AsyncFlagstaffClient
from httpx import AsyncClient

STACK_URL = os.environ.get("FLAGSTAFF_STACK_URL", "")
REPO_ROOT = Path(__file__).resolve().parents[3]
NEW_CHECKOUT = {
    "key": "new-checkout",
    "name": "New checkout",
    "kind": "boolean",
    "variants": [{"key": "on", "value": True}, {"key": "off", "value": False}],
    "off_variant": "off",
    "on_variant": "on",
}

pytestmark = pytest.mark.skipif(
    not STACK_URL, reason="needs the compose stack running and FLAGSTAFF_STACK_URL pointing at it"
)


def compose(*args: str) -> str:
    finished = subprocess.run(
        ["docker", "compose", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    )
    return finished.stdout


async def until(condition: Callable[[], bool], within: float = 10.0) -> None:
    async with asyncio.timeout(within):
        while not condition():
            await asyncio.sleep(0.05)


@pytest.fixture(scope="module")
def admin_key() -> str:
    return compose(
        "exec", "-T", "api-1", "flagstaff-server", "create-admin-key", "--name", "stack tests"
    ).strip()


@pytest.fixture
async def api(admin_key: str) -> AsyncIterator[AsyncClient]:
    headers = {"Authorization": f"Bearer {admin_key}"}
    async with AsyncClient(base_url=STACK_URL, headers=headers, timeout=10) as client:
        yield client


# The stack keeps its data between runs, so each test gets a project of its own.
@pytest.fixture
async def project(api: AsyncClient) -> str:
    key = f"stack-{uuid4().hex[:8]}"
    created = await api.post("/projects", json={"key": key, "name": "Stack test"})
    assert created.status_code == 201, created.text
    flag = await api.post(f"/projects/{key}/flags", json=NEW_CHECKOUT)
    assert flag.status_code == 201, flag.text
    return key


@pytest.fixture
async def flags(api: AsyncClient, project: str) -> AsyncIterator[AsyncFlagstaffClient]:
    issued = await api.post(
        "/api-keys",
        json={"kind": "sdk", "name": "stack tests", "project": project, "environment": "prod"},
    )
    assert issued.status_code == 201, issued.text
    async with AsyncFlagstaffClient(issued.json()["secret"], base_url=STACK_URL) as client:
        assert await client.wait_until_ready(timeout=10)
        yield client


async def enable_new_checkout(api: AsyncClient, project: str) -> None:
    response = await api.post(f"/projects/{project}/flags/new-checkout/environments/prod/enable")
    assert response.status_code == 200, response.text


def new_checkout_for(flags: AsyncFlagstaffClient) -> bool:
    return flags.bool_value("new-checkout", "user-7", default=False)


async def test_the_proxy_serves_the_api_but_not_its_metrics(api: AsyncClient) -> None:
    assert (await api.get("/health")).status_code == 200
    assert (await api.get("/metrics")).status_code == 404


async def test_the_proxy_serves_the_dashboard_beside_the_api() -> None:
    async with AsyncClient(base_url=STACK_URL, timeout=10) as browser:
        root = await browser.get("/")
        page = await browser.get("/dashboard/projects/storefront")
        api_answer = await browser.get("/projects")
        missing_asset = await browser.get("/dashboard/assets/missing.js")

    assert root.status_code == 302
    assert root.headers["Location"].endswith("/dashboard/")
    # A route inside the app is answered with the app, never cached, and with its policy.
    assert page.status_code == 200
    assert '<div id="root">' in page.text
    assert page.headers["Cache-Control"] == "no-cache"
    assert "default-src 'self'" in page.headers["Content-Security-Policy"]
    assert api_answer.status_code == 401
    assert "Content-Security-Policy" not in api_answer.headers
    assert missing_asset.status_code == 404


async def test_a_request_keeps_one_id_through_the_proxy(api: AsyncClient) -> None:
    named = await api.get("/projects", headers={"X-Request-ID": "stack-check-1"})
    unnamed = await api.get("/projects")

    assert named.headers["X-Request-ID"] == "stack-check-1"
    # nginx's own id, passed on so its log and the API's agree.
    assert re.fullmatch(r"[0-9a-f]{32}", unnamed.headers["X-Request-ID"])


async def test_an_edit_reaches_an_sdk_streaming_through_the_proxy(
    api: AsyncClient, project: str, flags: AsyncFlagstaffClient
) -> None:
    assert not new_checkout_for(flags)

    await enable_new_checkout(api, project)

    await until(lambda: new_checkout_for(flags))


async def test_an_sdk_rides_out_a_rolling_restart(
    api: AsyncClient, project: str, flags: AsyncFlagstaffClient
) -> None:
    for instance in ("api-1", "api-2"):
        await asyncio.to_thread(compose, "restart", instance)
        await asyncio.to_thread(compose, "up", "--wait", "--no-deps", "--no-recreate", instance)
        assert flags.is_ready

    await enable_new_checkout(api, project)

    await until(lambda: new_checkout_for(flags))
