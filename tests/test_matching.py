"""Erasure without disclosure, and the typo problem underneath it.

The tests that matter here are not the ones showing a match succeed. They
are the ones pinning down what the mechanism refuses, what it silently
misses, and how narrow the gap is between forgiving a typo and deleting a
stranger.
"""

import secrets

import pytest

from databank import Databank, Decision, Identity, Query
from databank.matching import (
    CANONICALISATION_VERSION,
    CandidateOutsideFingerprint,
    MATCH_THRESHOLD,
    ThresholdNotNegotiable,
    calibrate_threshold,
    canonicalise_address,
    canonicalise_identity,
    canonicalise_name,
    canonicalise_postcode,
    encode_for_private_match,
    erasure_receipt,
    fingerprint,
    identity_matches,
    private_match,
    select_candidates,
    similarity,
)

ALICE = "alice"
BROKER = "broker-7"

ALICE_IDENTITY = Identity("Alice", "Winterbourne", "Flat 3, 12 High Street", "Q12 8AB")

TYPO = Identity("Alice", "Wynterbourne", "12 High St, Apt 3", "q12 8ab")
INITIAL = Identity("A.", "Winterbourne", "Flat 3, 12 High Street", "Q12 8AB")
STRANGER = Identity("Alec", "Winterbourke", "14 High Street", "Q12 8AB")
UNRELATED = Identity("Bob", "Smith", "4 Elm Road", "V99 9ZZ")
OLD_ADDRESS = Identity("Alice", "Winterbourne", "7 Mill Lane", "Q11 5CD")


@pytest.fixture
def salt() -> bytes:
    return secrets.token_bytes(16)


@pytest.fixture
def bank() -> Databank:
    bank = Databank()
    bank.deposit(ALICE, "identity", ALICE_IDENTITY)
    bank.grant(ALICE, BROKER, "identity.matches_owner", "identity", quota_per_year=20)
    return bank


def match_query(candidate: Identity, salt: bytes, **extra) -> Query:
    return Query(
        requestor_id=BROKER,
        owner_id=ALICE,
        algorithm_id="identity.matches_owner",
        attribute="identity",
        parameters={
            "candidate": canonicalise_identity(candidate),
            "salt": salt,
            **extra,
        },
    )


# -- canonicalisation: the deterministic half ------------------------------


@pytest.mark.parametrize(
    "a,b",
    [
        ("O'Neill", "oneill"),
        ("Müller", "muller"),
        ("  van der  Berg ", "van der berg"),
        ("MacDonald-Smith", "macdonald smith"),
    ],
)
def test_name_formatting_folds_away(a: str, b: str) -> None:
    assert canonicalise_name(a) == canonicalise_name(b)


def test_transliteration_is_not_a_formatting_variant() -> None:
    """``Mueller`` is a different string, and honestly so.

    Folding it onto ``Müller`` would need a language-specific rule that also
    changes names it should not touch. It belongs to the fuzzy half.
    """
    assert canonicalise_name("Mueller") != canonicalise_name("Müller")


def test_diminutives_do_not_fold() -> None:
    assert canonicalise_name("Bob") != canonicalise_name("Robert")


@pytest.mark.parametrize(
    "a,b",
    [
        ("Flat 3, 12 High Street", "12 High St, Apt 3"),
        ("14 Elm Road", "14 Elm Rd."),
        ("The Old Rectory, 2 Church Lane", "Old Rectory, 2 Church Ln"),
    ],
)
def test_address_formatting_folds_away(a: str, b: str) -> None:
    assert canonicalise_address(a) == canonicalise_address(b)


def test_address_token_sorting_is_a_blunt_instrument() -> None:
    """Documented misbehaviour, not an accident.

    Sorting tokens is what makes ``Flat 3, 12 High Street`` agree with
    ``12 High St, Apt 3``. It also makes a Continental ordering agree, which
    is right, and it would make two different flats in one building agree if
    their numbers were transposed, which is not.
    """
    assert canonicalise_address("12 High Street") == canonicalise_address(
        "High Street 12"
    )


@pytest.mark.parametrize("raw", ["q12 8ab", "Q128AB", "Q12  8AB", "q12-8ab"])
def test_postcode_formatting_folds_away(raw: str) -> None:
    assert canonicalise_postcode(raw) == "Q128AB"


def test_canonicalisation_carries_its_version() -> None:
    assert canonicalise_identity(ALICE_IDENTITY).version == CANONICALISATION_VERSION


def test_cross_version_comparison_is_refused_not_guessed() -> None:
    """A version skew must not look like 'we do not hold you'."""
    a = canonicalise_identity(ALICE_IDENTITY)
    b = canonicalise_identity(ALICE_IDENTITY).__class__(
        *a.parts(), version="identity-canon/0"
    )
    with pytest.raises(ValueError, match="canonicalisation mismatch"):
        similarity(a, b)


# -- fingerprinting: coarse on purpose -------------------------------------


def test_fingerprint_survives_a_surname_typo(salt: bytes) -> None:
    owner = canonicalise_identity(ALICE_IDENTITY)
    assert fingerprint(canonicalise_identity(TYPO), salt) == fingerprint(owner, salt)


def test_fingerprint_is_shared_not_unique(salt: bytes) -> None:
    """A stranger falls in the same band. That is the feature."""
    owner = canonicalise_identity(ALICE_IDENTITY)
    assert fingerprint(canonicalise_identity(STRANGER), salt) == fingerprint(
        owner, salt
    )


def test_fingerprint_is_unlinkable_across_broadcasts() -> None:
    """Two erasure broadcasts must not be poolable into a register."""
    owner = canonicalise_identity(ALICE_IDENTITY)
    assert fingerprint(owner, secrets.token_bytes(16)) != fingerprint(
        owner, secrets.token_bytes(16)
    )


def test_a_house_move_puts_a_record_out_of_reach(salt: bytes) -> None:
    """The mechanism's worst failure, and it is silent.

    R-1005 is Alice's name, correctly spelt, at her pre-2019 address. It
    never enters the candidate set, so no query is ever asked about it and
    nothing appears on her statement. She cannot distinguish this from the
    broker not holding her at all.
    """
    owner = canonicalise_identity(ALICE_IDENTITY)
    band = fingerprint(owner, salt)
    records = [canonicalise_identity(i) for i in (TYPO, OLD_ADDRESS)]
    selected = select_candidates(records, band, salt)
    assert canonicalise_identity(TYPO) in selected
    assert canonicalise_identity(OLD_ADDRESS) not in selected


def test_fingerprint_width_is_bounded() -> None:
    owner = canonicalise_identity(ALICE_IDENTITY)
    with pytest.raises(ValueError):
        fingerprint(owner, b"salt", bits=4)


# -- matching: one bit, and a very narrow gap ------------------------------


def test_typo_and_initial_both_match(bank: Databank, salt: bytes) -> None:
    for candidate in (TYPO, INITIAL):
        result = bank.submit_query(match_query(candidate, salt))
        assert result.decision is Decision.ALLOW
        assert result.value is True
        assert result.bits_disclosed == 1


def test_stranger_survives(bank: Databank, salt: bytes) -> None:
    result = bank.submit_query(match_query(STRANGER, salt))
    assert result.value is False
    assert result.bits_disclosed == 1


def test_the_threshold_threads_a_very_narrow_gap() -> None:
    """The finding the whole module exists to record.

    The worst true match and the best false one are a few hundredths apart,
    and no amount of engineering widens that: a person one letter from you
    is genuinely almost you, to any matcher not permitted to look properly.
    Choosing where in the gap to sit is choosing whether the Owner's right
    or a stranger's record gives way.
    """
    owner = canonicalise_identity(ALICE_IDENTITY)
    true_match = min(
        similarity(owner, canonicalise_identity(i)) for i in (TYPO, INITIAL)
    )
    false_match = similarity(owner, canonicalise_identity(STRANGER))
    assert false_match < MATCH_THRESHOLD <= true_match
    assert 0 < true_match - false_match < 0.1


def test_a_looser_threshold_deletes_the_stranger() -> None:
    owner = canonicalise_identity(ALICE_IDENTITY)
    assert similarity(owner, canonicalise_identity(STRANGER)) >= 0.80


def test_exact_matching_would_have_erased_nothing() -> None:
    """What a deterministic hashed identifier -- DROP's design -- achieves."""
    owner = canonicalise_identity(ALICE_IDENTITY)
    for candidate in (TYPO, INITIAL, STRANGER, UNRELATED, OLD_ADDRESS):
        assert canonicalise_identity(candidate).parts() != owner.parts()


# -- refusals --------------------------------------------------------------


def test_requestor_may_not_choose_the_threshold(salt: bytes) -> None:
    with pytest.raises(ThresholdNotNegotiable):
        identity_matches(
            ALICE_IDENTITY, canonicalise_identity(TYPO), salt, threshold=0.5
        )


def test_candidate_must_lie_in_the_broadcast_band(salt: bytes) -> None:
    with pytest.raises(CandidateOutsideFingerprint):
        identity_matches(ALICE_IDENTITY, canonicalise_identity(UNRELATED), salt)


@pytest.mark.parametrize(
    "extra,candidate",
    [({"threshold": 0.5}, TYPO), ({}, UNRELATED)],
)
def test_refusals_are_denied_and_logged_not_raised(
    bank: Databank, salt: bytes, extra: dict, candidate: Identity
) -> None:
    """A refused probe must reach the Owner, not the requestor's traceback.

    An exception propagating to the broker would tell the one party that
    already knows what it tried. The Owner is the one who needs the line.
    """
    result = bank.submit_query(match_query(candidate, salt, **extra))
    assert result.decision is Decision.DENY
    assert result.bits_disclosed == 0
    assert "algorithm refused" in (result.reason or "")
    assert bank.statement(ALICE)[-1].decision is Decision.DENY


def test_a_refused_probe_still_costs_quota(salt: bytes) -> None:
    """Otherwise probing is free, and free probing is unbounded probing."""
    bank = Databank()
    bank.deposit(ALICE, "identity", ALICE_IDENTITY)
    bank.grant(ALICE, BROKER, "identity.matches_owner", "identity", quota_per_year=1)
    bank.submit_query(match_query(UNRELATED, salt))  # refused, quota consumed
    exhausted = bank.submit_query(match_query(TYPO, salt))
    assert exhausted.decision is Decision.DENY
    assert "quota" in (exhausted.reason or "")


def test_match_query_needs_a_standing_permission(salt: bytes) -> None:
    bank = Databank()
    bank.deposit(ALICE, "identity", ALICE_IDENTITY)
    result = bank.submit_query(match_query(TYPO, salt))
    assert result.decision is Decision.CONSENT_REQUIRED


# -- stubs -----------------------------------------------------------------


def test_privacy_preserving_matching_is_not_implemented(salt: bytes) -> None:
    """``similarity`` compares plaintext and claims nothing else.

    The encoding that would let two parties compare without disclosing is
    the stub, and it stays a stub until it arrives with a threat model:
    Bloom-filter record linkage preserves n-gram frequency and has been
    repeatedly broken by frequency alignment.
    """
    with pytest.raises(NotImplementedError):
        encode_for_private_match(canonicalise_identity(ALICE_IDENTITY), salt)
    with pytest.raises(NotImplementedError):
        private_match(b"", b"", 0.8)


def test_threshold_calibration_is_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        calibrate_threshold(1.0, 1.0)


def test_deletion_receipts_are_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        erasure_receipt(ALICE, BROKER, True)
