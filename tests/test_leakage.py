"""The retention-bounded leakage budget.

A requestor that bisects a date of birth with one-bit answers is the attack
bit-scarcity alone does not stop. These tests pin down the per-datum quota
that does.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from databank import Databank, Decision, Query
from databank.leakage import (
    DatumPolicy,
    LeakageBudget,
    adult_birth_date_policy,
    answers_to_resolve,
)

ALICE = "alice"
T0 = datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc)
AS_OF = date(2026, 6, 19)


def policy(**overrides) -> DatumPolicy:
    params = dict(
        group="birth_date",
        attributes=frozenset({"date_of_birth", "age"}),
        tau=timedelta(minutes=5),
        daily_quota=5,
        requestor_share=3,
        prior_range=70 * 365.25,
        resolution=365.25,
    )
    params.update(overrides)
    return DatumPolicy(**params)


# -- the bound itself ------------------------------------------------------


def test_answers_to_resolve_matches_the_tap_example() -> None:
    # An adult's birth date over ~70 years: ~15 answers to the day,
    # ~7 to the year.
    assert answers_to_resolve(70 * 365.25, 1) == 15
    assert answers_to_resolve(70 * 365.25, 365.25) == 7


def test_resolution_coarser_than_prior_needs_one_answer() -> None:
    assert answers_to_resolve(10, 20) == 1


def test_per_window_limit_and_frequency_are_derived() -> None:
    p = policy()
    assert p.per_window == p.answers_to_resolve - 1 == 6
    assert p.max_request_frequency == pytest.approx(6 / 300)


def test_child_prior_is_narrower_than_adult() -> None:
    adult = policy(prior_range=70 * 365.25)
    child = policy(prior_range=18 * 365.25)
    assert child.per_window < adult.per_window


@pytest.mark.parametrize(
    "overrides",
    [
        {"requestor_share": 5},  # share must be below the daily quota
        {"requestor_share": 0},
        {"daily_quota": 0},
        {"tau": timedelta(0)},  # tau = 0 is not achievable
        {"tau": timedelta(days=2)},
        {"attributes": frozenset()},
        {"prior_range": 1, "resolution": 1},  # no query admissible at all
    ],
)
def test_invalid_policies_are_rejected(overrides) -> None:
    with pytest.raises(ValueError):
        policy(**overrides)


def test_an_attribute_belongs_to_one_group_only() -> None:
    budget = LeakageBudget([policy()])
    with pytest.raises(ValueError):
        budget.add(policy(group="age_band", attributes=frozenset({"age"})))


# -- enforcement -----------------------------------------------------------


def run(budget: LeakageBudget, requestor: str, attribute: str, at: datetime):
    decision, reason = budget.check(ALICE, requestor, attribute, at)
    if decision is Decision.ALLOW:
        budget.consume(ALICE, requestor, attribute, at)
    return decision, reason


def test_quota_is_shared_by_all_requestors() -> None:
    budget = LeakageBudget([policy()])
    times = [T0 + timedelta(hours=h) for h in range(6)]
    requestors = ["a", "a", "b", "b", "c", "c"]
    decisions = [run(budget, r, "date_of_birth", t)[0] for r, t in zip(requestors, times)]
    assert decisions[:5] == [Decision.ALLOW] * 5
    assert decisions[5] is Decision.DENY
    assert budget.remaining(ALICE, "date_of_birth", times[-1]) == 0


def test_collusion_gains_no_extra_queries() -> None:
    budget = LeakageBudget([policy()])
    allowed = 0
    for i in range(20):
        decision, _ = run(budget, f"shell-{i}", "date_of_birth", T0 + timedelta(minutes=30 * i))
        allowed += decision is Decision.ALLOW
    assert allowed == 5


def test_one_requestor_cannot_exhaust_the_datum() -> None:
    budget = LeakageBudget([policy()])
    for h in range(3):
        assert run(budget, "greedy", "date_of_birth", T0 + timedelta(hours=h))[0] is Decision.ALLOW
    decision, reason = run(budget, "greedy", "date_of_birth", T0 + timedelta(hours=3))
    assert decision is Decision.DENY and "requestor share" in reason
    # A legitimate check from someone else still goes through.
    assert run(budget, "retailer", "date_of_birth", T0 + timedelta(hours=4))[0] is Decision.ALLOW


def test_correlated_attributes_share_one_quota() -> None:
    budget = LeakageBudget([policy()])
    run(budget, "a", "date_of_birth", T0)
    run(budget, "b", "age", T0 + timedelta(hours=1))
    assert budget.remaining(ALICE, "date_of_birth", T0 + timedelta(hours=1)) == 3


def test_retention_window_limit_applies_within_tau() -> None:
    # A generous daily quota, so only the per-tau limit binds.
    p = policy(daily_quota=50, requestor_share=40)
    budget = LeakageBudget([p])
    burst = [run(budget, "a", "date_of_birth", T0 + timedelta(seconds=i))[0] for i in range(p.per_window + 1)]
    assert burst[:-1] == [Decision.ALLOW] * p.per_window
    assert burst[-1] is Decision.DENY
    # Once tau has passed, what was held has expired and queries resume.
    later = T0 + p.tau + timedelta(seconds=p.per_window + 1)
    assert run(budget, "a", "date_of_birth", later)[0] is Decision.ALLOW


def test_budget_renews_after_a_day() -> None:
    budget = LeakageBudget([policy()])
    for i in range(5):
        run(budget, f"r{i}", "date_of_birth", T0 + timedelta(hours=i))
    assert run(budget, "r9", "date_of_birth", T0 + timedelta(hours=6))[0] is Decision.DENY
    assert run(budget, "r9", "date_of_birth", T0 + timedelta(days=1, minutes=1))[0] is Decision.ALLOW


def test_exempt_requestors_bypass_but_do_not_consume() -> None:
    budget = LeakageBudget([policy(exempt_requestors=frozenset({"police"}))])
    for i in range(10):
        assert run(budget, "police", "date_of_birth", T0 + timedelta(minutes=i))[0] is Decision.ALLOW
    assert budget.remaining(ALICE, "date_of_birth", T0 + timedelta(minutes=10)) == 5


def test_ungoverned_attributes_are_admitted() -> None:
    budget = LeakageBudget([policy()])
    assert budget.check(ALICE, "a", "identity", T0) == (Decision.ALLOW, None)
    assert budget.remaining(ALICE, "identity", T0) is None


# -- inside the Databank ---------------------------------------------------


def make_bank() -> Databank:
    bank = Databank(leakage=LeakageBudget([adult_birth_date_policy()]))
    bank.deposit(ALICE, "date_of_birth", date(1981, 4, 2))
    for requestor in ("probe", "retailer"):
        bank.grant(ALICE, requestor, "age.over_threshold", "date_of_birth")
    return bank


def age_query(requestor: str, threshold: int, at: datetime) -> Query:
    return Query(
        requestor_id=requestor,
        owner_id=ALICE,
        algorithm_id="age.over_threshold",
        attribute="date_of_birth",
        parameters={"threshold_years": threshold, "as_of": AS_OF},
        as_of=AS_OF,
        submitted_at=at,
    )


def test_bisecting_a_birth_year_is_cut_off_and_logged() -> None:
    bank = make_bank()
    lo, hi, answers = 18, 88, 0
    for i in range(10):
        mid = (lo + hi) // 2
        result = bank.submit_query(age_query("probe", mid, T0 + timedelta(minutes=i)))
        if not result.executed:
            break
        answers += 1
        lo, hi = (mid, hi) if result.value else (lo, mid)
    # The share of 3 answers leaves the year unresolved: a range of 70
    # years needs 7.
    assert answers == 3
    assert hi - lo > 1
    denied = [e for e in bank.statement(ALICE) if e.decision is Decision.DENY]
    assert denied and "requestor share" in denied[0].reason


def test_legitimate_check_survives_a_probe() -> None:
    bank = make_bank()
    for i in range(5):
        bank.submit_query(age_query("probe", 40 + i, T0 + timedelta(minutes=i)))
    result = bank.submit_query(age_query("retailer", 18, T0 + timedelta(minutes=10)))
    assert result.executed and result.value is True


def test_databank_without_a_budget_behaves_as_before() -> None:
    bank = Databank()
    bank.deposit(ALICE, "date_of_birth", date(1981, 4, 2))
    bank.grant(ALICE, "probe", "age.over_threshold", "date_of_birth")
    results = [bank.submit_query(age_query("probe", 18 + i, T0)) for i in range(10)]
    assert all(r.executed for r in results)
