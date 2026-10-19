from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from flagstaff_server.domain.api_keys import ApiKey, ApiKeyKind
from flagstaff_server.domain.errors import InvalidValueError
from flagstaff_server.domain.ids import ApiKeyId, EnvironmentId
from flagstaff_server.domain.values import Name

AT = datetime(2026, 10, 19, 9, 30, tzinfo=UTC)
PROD = EnvironmentId(uuid4())
STAGING = EnvironmentId(uuid4())


def admin_key() -> ApiKey:
    return ApiKey.admin(key_id=ApiKeyId(uuid4()), name=Name("Release tooling"), at=AT)


def sdk_key(environment_id: EnvironmentId = PROD) -> ApiKey:
    return ApiKey.sdk(
        key_id=ApiKeyId(uuid4()), name=Name("checkout-api"), environment_id=environment_id, at=AT
    )


def test_an_admin_key_manages_and_reads_everything() -> None:
    key = admin_key()

    assert key.can_manage
    assert key.can_read(PROD)
    assert key.can_read(STAGING)


def test_an_sdk_key_reads_only_its_own_environment() -> None:
    key = sdk_key(PROD)

    assert not key.can_manage
    assert key.can_read(PROD)
    assert not key.can_read(STAGING)


@pytest.mark.parametrize("make_key", [admin_key, sdk_key])
def test_a_revoked_key_can_do_nothing(make_key: Callable[[], ApiKey]) -> None:
    key = make_key()

    assert key.revoke(at=AT) is True

    assert not key.is_active
    assert key.revoked_at == AT
    assert not key.can_manage
    assert not key.can_read(PROD)


def test_revoking_twice_changes_nothing_the_second_time() -> None:
    key = sdk_key()
    key.revoke(at=AT)

    assert key.revoke(at=datetime(2026, 10, 20, tzinfo=UTC)) is False
    assert key.revoked_at == AT


@pytest.mark.parametrize(
    ("kind", "environment_id"), [(ApiKeyKind.SDK, None), (ApiKeyKind.ADMIN, PROD)]
)
def test_only_sdk_keys_belong_to_an_environment(
    kind: ApiKeyKind, environment_id: EnvironmentId | None
) -> None:
    with pytest.raises(InvalidValueError, match="exactly one environment"):
        ApiKey(
            key_id=ApiKeyId(uuid4()),
            kind=kind,
            name=Name("checkout-api"),
            environment_id=environment_id,
            created_at=AT,
        )
