"""The worked example from https://databanking.org/worked-example.html

Alice holds her date of birth with her Databank. A retailer needs to know
whether she is over 18. Run this file to watch exactly what crosses the
boundary.

    python examples/age_check.py
"""

from datetime import date

from databank import Databank, Query

ALICE = "alice"
RETAILER = "retailer-42"


def main() -> None:
    bank = Databank()

    # (0) Alice deposits her date of birth, and pre-authorises age-threshold
    #     checks from this retailer -- twice per year, no more.
    bank.deposit(ALICE, "date_of_birth", date(2007, 4, 2))
    bank.grant(
        owner_id=ALICE,
        requestor_id=RETAILER,
        algorithm_id="age.over_threshold",
        attribute="date_of_birth",
        quota_per_year=2,
    )

    query = Query(
        requestor_id=RETAILER,
        owner_id=ALICE,
        algorithm_id="age.over_threshold",
        attribute="date_of_birth",
        parameters={"threshold_years": 18, "as_of": date(2026, 6, 19)},
        as_of=date(2026, 6, 19),
    )

    # (1-4) Submit, check, execute, return.
    result = bank.submit_query(query)
    print(f"decision        : {result.decision.value}")
    print(f"value returned  : {result.value}")
    print(f"bits disclosed  : {result.bits_disclosed}")

    # The retailer has an answer. It does not have -- and cannot derive --
    # Alice's date of birth.
    assert result.value is True
    assert result.bits_disclosed == 1

    # (5) Alice's statement.
    print("\nAlice's statement:")
    for entry in bank.statement(ALICE):
        print(
            f"  {entry.timestamp:%Y-%m-%d %H:%M}  {entry.requestor_id}"
            f"  {entry.algorithm_id}  {entry.decision.value}"
            f"  ({entry.bits_disclosed} bit)"
        )

    # A third attempt in the same year exhausts the quota Alice set.
    bank.submit_query(query)
    exhausted = bank.submit_query(query)
    print(f"\nthird query     : {exhausted.decision.value} -- {exhausted.reason}")


if __name__ == "__main__":
    main()
