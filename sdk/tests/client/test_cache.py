import logging
from pathlib import Path

import pytest

from flagstaff._cache import RulesetFile
from tests.client.rulesets import storefront


def test_a_saved_ruleset_loads_back_as_it_was(tmp_path: Path) -> None:
    cache = RulesetFile(tmp_path / "flagstaff" / "prod.json")

    cache.save(storefront(12))

    assert cache.load() == storefront(12)


def test_saving_again_replaces_the_previous_ruleset(tmp_path: Path) -> None:
    cache = RulesetFile(tmp_path / "prod.json")
    cache.save(storefront(12))

    cache.save(storefront(13))

    loaded = cache.load()
    assert loaded is not None
    assert loaded.version == 13
    assert [path.name for path in tmp_path.iterdir()] == ["prod.json"]


def test_a_missing_cache_is_simply_empty(tmp_path: Path) -> None:
    assert RulesetFile(tmp_path / "prod.json").load() is None


@pytest.mark.parametrize(
    "content",
    ["", "{not json", '{"format": 99, "version": 1, "flags": []}'],
    ids=["empty", "garbled", "newer format"],
)
def test_an_unreadable_cache_is_ignored_with_a_warning(
    tmp_path: Path, content: str, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "prod.json"
    path.write_text(content, encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="flagstaff"):
        assert RulesetFile(path).load() is None

    assert "ignored an unreadable ruleset cache" in caplog.text


def test_a_cache_it_cannot_write_is_reported_not_raised(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    blocked = tmp_path / "taken"
    blocked.write_text("a file where the cache directory should be", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="flagstaff"):
        RulesetFile(blocked / "prod.json").save(storefront(12))

    assert "could not write the ruleset cache" in caplog.text
