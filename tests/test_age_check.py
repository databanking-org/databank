from datetime import date

import pytest

from databank import Databank, Decision, Query

ALICE = "alice"
RETAILER = "retailer-42"
AS_OF = date(2026, 6, 19)


@pytest.fixture
def bank() -> Databank:
    bank = Databank()
    bank.deposit(ALICE, "date_of_birth", date(2007, 4, 2))
    bank.grant(ALICE, RETAILER, "age.over_threshold", "date_of_birth", quota_per_year=2)
    return bank


def age_query(threshold: int = 18, as_of: date = AS_OF) -> Query:
    return Query(
        requestor_id=RETAILER,
        owner_id=ALICE,
        algorithm_id="age.over_threshold",
        attribute="date_of_birth",
        parameters={"threshold_years": threshold, "as_of": as_of},
        as_of=as_of,
    )


def test_over_eighteen_returns_one_bit(bank: Databank) -> None:
    result = bank.submit_query(age_query())
    assert result.decision is Decision.ALLOW
    assert result.value is True
    assert result.bits_disclosed == 1


def test_under_threshold_returns_false(bank: Databank) -> None:
    result = bank.submit_query(age_query(threshold=25))
    assert result.value is False
    assert result.bits_disclosed == 1


def test_boundary_on_exact_birthday(bank: Databank) -> None:
    on_birthday = bank.submit_query(age_query(as_of=date(2025, 4, 2)))
    day_before = bank.submit_query(age_query(as_of=date(2025, 4, 1)))
    assert on_birthday.value is True
    assert day_before.value is False


def test_result_carries_no_date_of_birth(bank: Databank) -> None:
    result = bank.submit_query(age_query())
    assert "2007" not in repr(result)
    assert isinstance(result.value, bool)


def test_query_is_logged_on_the_owner_statement(bank: Databank) -> None:
    bank.submit_query(age_query())
    (entry,) = bank.statement(ALICE)
    assert entry.requestor_id == RETAILER
    assert entry.decision is Decision.ALLOW
    assert entry.bits_disclosed == 1


def test_missing_record_is_denied_and_logged() -> None:
    bank = Databank()
    bank.grant(ALICE, RETAILER, "age.over_threshold", "date_of_birth")
    result = bank.submit_query(age_query())
    assert result.decision is Decision.DENY
    assert "no record" in result.reason
    assert len(bank.statement(ALICE)) == 1


def test_erasure_removes_the_record_but_keeps_the_trail(bank: Databank) -> None:
    bank.submit_query(age_query())
    assert bank.erase(ALICE, "date_of_birth") is True
    after = bank.submit_query(age_query())
    assert after.decision is Decision.DENY
    assert len(bank.statement(ALICE)) == 2
