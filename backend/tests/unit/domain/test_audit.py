from datetime import UTC, datetime
from uuid import uuid4

from flagstaff_server.domain.api_keys import ApiKey
from flagstaff_server.domain.audit import Actor
from flagstaff_server.domain.ids import ApiKeyId
from flagstaff_server.domain.values import Name


def test_an_actor_remembers_the_name_of_the_key_that_acted() -> None:
    key = ApiKey.admin(
        key_id=ApiKeyId(uuid4()),
        name=Name("Release tooling"),
        at=datetime(2026, 10, 19, tzinfo=UTC),
    )

    assert Actor.of(key) == Actor(key.id, "Release tooling")


def test_the_command_line_acts_without_a_key() -> None:
    assert Actor.command_line().api_key_id is None
