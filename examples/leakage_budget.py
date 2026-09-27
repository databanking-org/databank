"""Bisecting a birthday, and the quota that stops it.

Every answer here is one bit: "is Alice at least 18 on this date?". Asked
once, it tells a retailer what it needs. Asked on successive dates, halving
the interval each time, it recovers her exact date of birth: about nine
questions once the year is known, about fifteen from scratch. Bit-scarcity
alone does not stop that.

The retention-bounded leakage budget does. A requestor may hold an answer
only for a few minutes, so bisection needs the answers to be kept
unlawfully, and the Databank caps queries on the datum -- shared by all
requestors, with a smaller share for each -- well below what bisection needs.

    python examples/leakage_budget.py
"""

from datetime import date, datetime, timedelta, timezone

from databank import Databank, Decision, Query
from databank.leakage import LeakageBudget, adult_birth_date_policy

ALICE = "alice"
PROBE = "data-broker-7"
RETAILER = "retailer-42"
BORN = date(2007, 4, 2)
T0 = datetime(2026, 9, 27, 9, 0, tzinfo=timezone.utc)


def eighteen_on(requestor: str, day: date, at: datetime) -> Query:
    return Query(
        requestor_id=requestor,
        owner_id=ALICE,
        algorithm_id="age.over_threshold",
        attribute="date_of_birth",
        parameters={"threshold_years": 18, "as_of": day},
        as_of=day,
        submitted_at=at,
    )


def bisect(bank: Databank, label: str) -> None:
    lo, hi = date(2025, 1, 1), date(2025, 12, 31)  # she turns 18 in 2025
    asked = 0
    print(f"\n{label}")
    while lo < hi:
        mid = lo + (hi - lo) // 2
        result = bank.submit_query(eighteen_on(PROBE, mid, T0 + timedelta(minutes=asked)))
        if result.decision is not Decision.ALLOW:
            print(f"  query {asked + 1:2d}: {result.decision.value} -- {result.reason}")
            break
        asked += 1
        lo, hi = (lo, mid) if result.value else (mid + timedelta(days=1), hi)
    span = (hi - lo).days + 1
    outcome = f"birthday pinned to {lo:%d %b}" if span == 1 else f"still {span} days wide"
    print(f"  {asked} one-bit answers, {outcome}")


def main() -> None:
    policy = adult_birth_date_policy()
    print(
        f"policy: {policy.daily_quota} queries/day on {policy.group!r}, "
        f"{policy.requestor_share} per requestor, at most {policy.per_window} "
        f"per {policy.tau} retention window"
    )

    # Without a budget: every answer is one bit, and the birthday falls out.
    open_bank = Databank()
    open_bank.deposit(ALICE, "date_of_birth", BORN)
    open_bank.grant(ALICE, PROBE, "age.over_threshold", "date_of_birth")
    bisect(open_bank, "without a leakage budget")

    # With one: the probe runs out of share long before the birthday does.
    bank = Databank(leakage=LeakageBudget([policy]))
    bank.deposit(ALICE, "date_of_birth", BORN)
    for requestor in (PROBE, RETAILER):
        bank.grant(ALICE, requestor, "age.over_threshold", "date_of_birth")
    bisect(bank, "with the retention-bounded leakage budget")

    # The probe's share is spent; a legitimate check still goes through.
    check = bank.submit_query(eighteen_on(RETAILER, date(2026, 6, 19), T0 + timedelta(minutes=30)))
    print(f"\nretailer's age check afterwards: {check.decision.value}, value {check.value}")

    print("\nAlice's statement:")
    for entry in bank.statement(ALICE):
        note = f" -- {entry.reason}" if entry.reason else ""
        print(f"  {entry.requestor_id:14s} {entry.decision.value:5s}{note}")


if __name__ == "__main__":
    main()
