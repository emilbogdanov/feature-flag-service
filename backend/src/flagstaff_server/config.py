from typing import Literal

from pydantic import PositiveFloat, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FLAGSTAFF_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # JSON for anything that ships logs somewhere; text is easier to read in a terminal.
    log_format: Literal["json", "text"] = "json"
    database_url: PostgresDsn
    # Carries flag-change notifications between API instances so every SSE stream hears them.
    redis_url: RedisDsn
    # How long a quiet stream waits before sending a keep-alive, below the idle timeout of any
    # proxy in front of the API.
    stream_heartbeat_seconds: PositiveFloat = 15.0
    # How often each instance checks its streams' versions against the database, in case a
    # change notification was lost; the most a stream can fall behind while Redis is down.
    ruleset_resync_seconds: PositiveFloat = 30.0
