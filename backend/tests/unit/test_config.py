import pytest
from pydantic import ValidationError

from flagstaff_server.config import Settings

VALID_ENV = {
    "FLAGSTAFF_DATABASE_URL": "postgresql+asyncpg://flagstaff:flagstaff@db:5432/flagstaff",
    "FLAGSTAFF_REDIS_URL": "redis://cache:6379/0",
}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name, value in VALID_ENV.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


def load_settings() -> Settings:
    # A developer's local .env must not leak into the test run.
    return Settings(_env_file=None)


def test_reads_prefixed_environment_variables(env: pytest.MonkeyPatch) -> None:
    env.setenv("FLAGSTAFF_LOG_LEVEL", "DEBUG")
    env.setenv("FLAGSTAFF_LOG_FORMAT", "text")

    settings = load_settings()

    assert str(settings.database_url) == VALID_ENV["FLAGSTAFF_DATABASE_URL"]
    assert str(settings.redis_url) == VALID_ENV["FLAGSTAFF_REDIS_URL"]
    assert settings.log_level == "DEBUG"
    assert settings.log_format == "text"


@pytest.mark.usefixtures("env")
def test_defaults_suit_a_production_deployment() -> None:
    settings = load_settings()

    assert settings.log_level == "INFO"
    assert settings.log_format == "json"
    assert settings.stream_heartbeat_seconds == 15.0
    assert settings.ruleset_resync_seconds == 30.0
    assert settings.key_cache_seconds == 10.0
    assert settings.version_cache_seconds == 5.0


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("FLAGSTAFF_DATABASE_URL", "mysql://flagstaff:flagstaff@db:3306/flagstaff"),
        ("FLAGSTAFF_REDIS_URL", "http://cache:6379"),
        ("FLAGSTAFF_LOG_LEVEL", "VERBOSE"),
        ("FLAGSTAFF_LOG_FORMAT", "xml"),
        ("FLAGSTAFF_STREAM_HEARTBEAT_SECONDS", "0"),
        ("FLAGSTAFF_RULESET_RESYNC_SECONDS", "-5"),
        ("FLAGSTAFF_KEY_CACHE_SECONDS", "-1"),
        ("FLAGSTAFF_VERSION_CACHE_SECONDS", "soon"),
    ],
)
def test_rejects_invalid_values(env: pytest.MonkeyPatch, name: str, value: str) -> None:
    env.setenv(name, value)

    with pytest.raises(ValidationError, match=name.removeprefix("FLAGSTAFF_").lower()):
        load_settings()


@pytest.mark.parametrize("name", list(VALID_ENV))
def test_connection_urls_are_required(env: pytest.MonkeyPatch, name: str) -> None:
    env.delenv(name)

    with pytest.raises(ValidationError, match=name.removeprefix("FLAGSTAFF_").lower()):
        load_settings()
