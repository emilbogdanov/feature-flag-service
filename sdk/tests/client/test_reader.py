import logging

import pytest

from flagstaff._store import RulesetStore
from flagstaff.engine.context import EvaluationContext
from flagstaff.reader import FlagReader, Reason
from tests.client.rulesets import storefront


@pytest.fixture
def store() -> RulesetStore:
    store = RulesetStore()
    store.replace(storefront(7))
    return store


@pytest.fixture
def flags(store: RulesetStore) -> FlagReader:
    return FlagReader(store)


class TestEvaluating:
    def test_reads_each_kind_of_flag(self, flags: FlagReader) -> None:
        user = EvaluationContext("user-310", {"country": "BG"})

        assert flags.bool_value("new-checkout", user, default=True) is False
        assert flags.str_value("checkout-theme", user, default="classic") == "spruce"
        assert flags.number_value("search-results-per-page", user, default=24) == 48
        assert flags.json_value("upload-limits", user, default={}) == {
            "per_day": 500,
            "formats": ["png", "webp"],
        }

    def test_a_bare_user_key_is_a_context_without_attributes(self, flags: FlagReader) -> None:
        assert flags.bool_value("new-checkout", "user-7", default=False) is True

    def test_says_which_rule_served_the_value(self, flags: FlagReader) -> None:
        detail = flags.bool_detail("new-checkout", "user-7", default=False)

        assert (detail.value, detail.variant, detail.reason, detail.rule_id) == (
            True,
            "on",
            Reason.RULE_MATCH,
            "testers",
        )
        assert detail.ruleset_version == 7

    def test_a_disabled_flag_serves_its_off_variant(self) -> None:
        store = RulesetStore()
        store.replace(storefront(8, checkout_enabled=False))

        detail = FlagReader(store).bool_detail("new-checkout", "user-7", default=True)

        assert (detail.value, detail.reason) == (False, Reason.DISABLED)

    def test_a_json_value_can_be_changed_without_changing_the_flag(self, flags: FlagReader) -> None:
        limits = flags.json_value("upload-limits", "user-310", default={})
        assert isinstance(limits, dict)
        limits["per_day"] = 1_000_000

        assert flags.json_value("upload-limits", "user-310", default={}) == {
            "per_day": 500,
            "formats": ["png", "webp"],
        }


class TestFallingBack:
    def test_before_any_rules_arrive_the_default_is_served(self) -> None:
        detail = FlagReader(RulesetStore()).bool_detail("new-checkout", "user-7", default=True)

        assert (detail.value, detail.variant, detail.reason) == (True, None, Reason.NOT_READY)
        assert detail.ruleset_version is None

    def test_an_unknown_flag_serves_the_default(self, flags: FlagReader) -> None:
        detail = flags.str_detail("checkout-colour", "user-7", default="classic")

        assert (detail.value, detail.reason, detail.ruleset_version) == (
            "classic",
            Reason.FLAG_NOT_FOUND,
            7,
        )

    def test_asking_for_the_wrong_type_serves_the_default(self, flags: FlagReader) -> None:
        as_bool = flags.bool_detail("checkout-theme", "user-7", default=False)
        as_number = flags.number_detail("checkout-theme", "user-7", default=0)

        assert (as_bool.value, as_bool.reason) == (False, Reason.WRONG_TYPE)
        assert (as_number.value, as_number.reason) == (0, Reason.WRONG_TYPE)

    def test_a_boolean_is_not_a_number(self, flags: FlagReader) -> None:
        assert flags.number_value("new-checkout", "user-7", default=3) == 3

    def test_an_empty_user_key_serves_the_default(self, flags: FlagReader) -> None:
        detail = flags.bool_detail("new-checkout", "", default=True)

        assert (detail.value, detail.reason) == (True, Reason.INVALID_CONTEXT)

    def test_warns_once_per_flag_and_reason(
        self, flags: FlagReader, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="flagstaff"):
            for _ in range(3):
                flags.bool_value("checkout-colour", "user-7", default=False)
            flags.bool_value("checkout-theme", "user-7", default=False)

        assert [record.getMessage() for record in caplog.records] == [
            "flag 'checkout-colour' served the default because of flag_not_found",
            "flag 'checkout-theme' served the default because of wrong_type",
        ]


def test_reports_readiness_and_version(flags: FlagReader) -> None:
    assert flags.is_ready
    assert flags.ruleset_version == 7
    assert not FlagReader(RulesetStore()).is_ready
