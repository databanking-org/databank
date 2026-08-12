from datetime import date

import pytest

from databank import Databank, Decision, Query

ALICE = "alice"
RETAILER = "retailer-42"
STRANGER = "data-broker-9"
AS_OF = date(2026, 6, 19)


def query(requestor: str = RETAILER, as_of: date = AS_OF) -> Query:
    return Query(
        requestor_id=requestor,
        owner_id=ALICE,
        algorithm_id="age.over_threshold",
        attribute="date_of_birth",
        parameters={"threshold_years": 18, "as_of": as_of},
        as_of=as_of,
    )


@pytest.fixture
def bank() -> Databank:
    bank = Databank()
    bank.deposit(ALICE, "date_of_birth", date(2007, 4, 2))
    bank.grant(ALICE, RETAILER, "age.over_threshold", "date_of_birth", quota_per_year=2)
    return bank


def test_unknown_requestor_needs_consent_not_denial(bank: Databank) -> None:
    result = bank.submit_query(query(requestor=STRANGER))
    assert result.decision is Decision.CONSENT_REQUIRED
    assert result.value is None
    assert result.bits_disclosed == 0


def test_denied_query_is_still_logged(bank: Databank) -> None:
    bank.submit_query(query(requestor=STRANGER))
    (entry,) = bank.statement(ALICE)
    assert entry.decision is Decision.CONSENT_REQUIRED
    assert entry.requestor_id == STRANGER


def test_quota_is_enforced_within_the_year(bank: Databank) -> None:
    assert bank.submit_query(query()).decision is Decision.ALLOW
    assert bank.submit_query(query()).decision is Decision.ALLOW
    third = bank.submit_query(query())
    assert third.decision is Decision.DENY
    assert "quota" in third.reason


def test_quota_resets_the_following_year(bank: Databank) -> None:
    bank.submit_query(query())
    bank.submit_query(query())
    assert bank.submit_query(query()).decision is Decision.DENY
    next_year = bank.submit_query(query(as_of=date(2027, 6, 19)))
    assert next_year.decision is Decision.ALLOW


def test_revocation_takes_effect_immediately(bank: Databank) -> None:
    assert bank.submit_query(query()).decision is Decision.ALLOW
    assert bank.revoke(ALICE, RETAILER, "age.over_threshold") == 1
    assert bank.submit_query(query()).decision is Decision.CONSENT_REQUIRED


def test_algorithm_cannot_be_pointed_at_another_attribute(bank: Databank) -> None:
    mismatched = Query(
        requestor_id=RETAILER,
        owner_id=ALICE,
        algorithm_id="age.over_threshold",
        attribute="health_record",
        parameters={"threshold_years": 18, "as_of": AS_OF},
        as_of=AS_OF,
    )
    result = bank.submit_query(mismatched)
    assert result.decision is Decision.DENY
    assert "date_of_birth" in result.reason
