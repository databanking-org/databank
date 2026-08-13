"""Erasure without disclosure, and what a typo does to it.

The case study at https://databanking.org/right-to-be-deleted.html. Alice
wants her record erased from a data broker. Under every mechanism available
today she must first hand that broker enough identifying data to find her.
Here she hands over a lossy fingerprint, the broker matches inside the
sandbox, and one bit comes back.

Run this file to watch it work -- and then to watch the two places where it
does not.

    python examples/erasure_request.py
"""

import secrets

from databank import (
    Databank,
    Decision,
    Identity,
    Query,
    canonicalise_identity,
    fingerprint,
    select_candidates,
)
from databank.matching import FINGERPRINT_BITS, MATCH_THRESHOLD, similarity

ALICE = "alice"
BROKER = "broker-7"

# Every name and address below is invented. The postcodes are invented
# unusually hard: Q, V and X are never used as the first letter of a UK
# postcode area, so nothing here can collide with a real address. Worth the
# care in an example whose whole subject is data people want removed.

# What Alice's Databank holds. Correct, current, and never disclosed.
ALICE_IDENTITY = Identity(
    given_name="Alice",
    family_name="Winterbourne",
    address="Flat 3, 12 High Street",
    postcode="Q12 8AB",
)

# What the broker holds. Assembled over years from a dozen sources, with the
# data quality that implies.
BROKER_RECORDS = {
    "R-1001": Identity("Alice", "Wynterbourne", "12 High St, Apt 3", "q12 8ab"),
    "R-1002": Identity("A.", "Winterbourne", "Flat 3, 12 High Street", "Q12 8AB"),
    "R-1003": Identity("Alec", "Winterbourke", "14 High Street", "Q12 8AB"),
    "R-1004": Identity("Bob", "Smith", "4 Elm Road", "V99 9ZZ"),
    # Alice's address until 2019. Correct when it was recorded; correct in
    # the broker's files still. Watch what happens to it.
    "R-1005": Identity("Alice", "Winterbourne", "7 Mill Lane", "Q11 5CD"),
}


def rule(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def main() -> None:
    bank = Databank()
    bank.deposit(ALICE, "identity", ALICE_IDENTITY)
    bank.grant(
        owner_id=ALICE,
        requestor_id=BROKER,
        algorithm_id="identity.matches_owner",
        attribute="identity",
        quota_per_year=8,
    )

    canonical = canonicalise_identity(ALICE_IDENTITY)

    # (0) The broadcast. A fresh salt per broadcast, so that companies
    #     receiving it cannot pool their lists into a register of everyone
    #     who has asked to be forgotten.
    salt = secrets.token_bytes(16)
    band = fingerprint(canonical, salt)

    rule("What the broker receives")
    print(f"fingerprint band : 0x{band:05x}  ({FINGERPRINT_BITS} bits, shared by many people)")
    print("link token       : authorises match queries against Alice's Databank")
    print("Alice's name     : not sent")
    print("Alice's address  : not sent")

    # (1) The broker narrows locally, against its own data. No query, no fee,
    #     no disclosure -- it is only looking at records it already holds.
    canonical_records = {
        ref: canonicalise_identity(identity)
        for ref, identity in BROKER_RECORDS.items()
    }
    in_band = {
        ref: rec
        for ref, rec in canonical_records.items()
        if rec in select_candidates([rec], band, salt)
    }

    rule("Candidate selection, on the broker's side")
    for ref in canonical_records:
        selected = "candidate" if ref in in_band else "-"
        print(f"  {ref}  {BROKER_RECORDS[ref].family_name:<14} {selected}")

    # (2) One match query per candidate. The broker's record and Alice's meet
    #     inside the sandbox and nowhere else.
    rule(f"Match queries (threshold {MATCH_THRESHOLD}, fixed by the protocol)")
    deleted = []
    for ref, record in in_band.items():
        result = bank.submit_query(
            Query(
                requestor_id=BROKER,
                owner_id=ALICE,
                algorithm_id="identity.matches_owner",
                attribute="identity",
                parameters={"candidate": record, "salt": salt},
            )
        )
        verdict = "DELETE" if result.value else "keep"
        # Printed here only to explain the demo. The broker never sees it:
        # the score is computed inside the sandbox and thresholded there,
        # and QueryResult carries the bit alone.
        score = similarity(canonical, record)
        print(
            f"  {ref}  {result.value!s:<5} "
            f"({result.bits_disclosed} bit)  ->  {verdict:<6}"
            f"        [score {score:.3f}, not disclosed]"
        )
        if result.value:
            deleted.append(ref)

    print(f"\n  broker deletes: {', '.join(deleted)}")

    # (3) The typo, which is the point of the exercise.
    rule("What an exact-match scheme would have done")
    for ref, record in canonical_records.items():
        agrees = record.parts() == canonical.parts()
        print(f"  {ref}  {'match' if agrees else 'no match'}")
    print(
        "\n  Nothing. R-1001 differs by one letter of Alice's surname and\n"
        "  R-1002 by an abbreviated forename. A hashed identifier -- DROP's\n"
        "  design -- matches neither, and reports no failure: to Alice,\n"
        "  'we mistyped your name' and 'we do not hold you' are the same\n"
        "  silence."
    )

    rule("Where canonicalisation ends and tolerance begins")
    print("  R-1002 address  '12 High St, Apt 3'   -> canonicalised, exact")
    print("  R-1001 postcode 'q12 8ab'             -> canonicalised, exact")
    print("  R-1001 surname  'Wynterbourne'        -> needs the threshold")
    print("  R-1002 forename 'A.'                  -> needs the threshold")
    print(
        "\n  Formatting is deterministic and free. Genuine error is neither,\n"
        "  and everything below is the price of forgiving it."
    )

    # (4) The stranger. R-1003 is a different person, in the same band, one
    #     letter from Alice's surname.
    rule("The cost, paid by someone who asked for nothing")
    worst_match = min(similarity(canonical, canonical_records[r]) for r in deleted)
    stranger = similarity(canonical, canonical_records["R-1003"])
    print(f"  R-1002  Alice, badly recorded          score {worst_match:.3f}  deleted")
    print(f"  R-1003  Alec, a different person       score {stranger:.3f}  survives")
    print(f"\n  The threshold has to fall inside a gap {worst_match - stranger:.3f} wide.")
    print(
        "  Nudge it up and Alice's own record survives her broker's typo;\n"
        "  nudge it down and a stranger's record is destroyed -- and he is\n"
        "  never told, and no party to the transaction can detect that it\n"
        "  happened. Nothing about that gap widens with better engineering:\n"
        "  a person one letter from you is genuinely almost you, by every\n"
        "  measure available to a matcher that is not allowed to look. The\n"
        "  threshold is not a tuning parameter. It decides who pays for the\n"
        "  broker's bad data -- see matching.calibrate_threshold."
    )

    # (5) The record the mechanism cannot reach at all.
    rule("The record that was never asked about")
    stale = canonical_records["R-1005"]
    print("  R-1005 'Alice Winterbourne, 7 Mill Lane, Q11 5CD'")
    print(f"  band 0x{fingerprint(stale, salt):05x} != 0x{band:05x}")
    print(
        "\n  Alice's own name, spelt correctly, at the address she left in\n"
        "  2019. The fingerprint keys on the postcode district, so a house\n"
        "  move puts a record permanently out of reach -- not refused, not\n"
        "  logged, never selected. Alice's statement below shows three\n"
        "  queries and no sign that a fifth record exists. Broadcasting\n"
        "  historical addresses would reach it, and would also widen the\n"
        "  fingerprint into something closer to an identifier."
    )

    # (6) Two things the sandbox refuses -- and puts on Alice's statement.
    rule("Refusals")
    probes = {
        "requestor-chosen threshold": {
            "candidate": canonical_records["R-1001"],
            "salt": salt,
            "threshold": 0.5,
        },
        "out-of-band candidate": {
            "candidate": canonical_records["R-1004"],
            "salt": salt,
        },
    }
    for label, parameters in probes.items():
        refused = bank.submit_query(
            Query(
                requestor_id=BROKER,
                owner_id=ALICE,
                algorithm_id="identity.matches_owner",
                attribute="identity",
                parameters=parameters,
            )
        )
        assert refused.decision is Decision.DENY
        print(f"  {label}\n    {refused.reason}\n")

    print(
        "\n  Neither refusal makes this probe-proof. Inside the band a broker\n"
        "  can still vary a spelling and watch for the answer to flip,\n"
        "  recovering the true string from the shape of the threshold ball --\n"
        "  the same attack as binary-searching a birth year with repeated\n"
        "  age checks. Quota, fee and audit trail are what bound it, and\n"
        "  bounding it properly is bitbudget.cumulative_leakage_bound, which\n"
        "  is a stub."
    )

    # (7) Alice's statement. Every query, including the ones she would want
    #     to ask about.
    rule("Alice's statement")
    for entry in bank.statement(ALICE):
        note = f"  {entry.reason}" if entry.reason else ""
        print(
            f"  {entry.timestamp:%Y-%m-%d %H:%M}  {entry.requestor_id}"
            f"  {entry.algorithm_id}  {entry.decision.value}"
            f"  ({entry.bits_disclosed} bit){note}"
        )
    print(
        f"\n  {len([e for e in bank.statement(ALICE) if e.decision is Decision.ALLOW])}"
        " bits disclosed in total, to erase a record the broker should not\n"
        "  have needed her name to find."
    )


if __name__ == "__main__":
    main()
