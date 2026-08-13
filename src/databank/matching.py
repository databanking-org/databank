"""Identity matching for erasure without disclosure.

The case study at https://databanking.org/right-to-be-deleted.html: an Owner
wants their record erased from a company that holds it, without handing that
company the identifying data it would need to find the record -- which is
what every existing erasure route, including California's DROP, requires.

The flow modelled here:

1. The Owner's Databank broadcasts a **fingerprint**: a salted, deliberately
   lossy digest of coarse identity features. It is not an identifier. Many
   people share one.
2. The company selects its **candidate records** locally -- the ones whose
   own fingerprint falls in the same band. It learns nothing it did not
   already hold.
3. For each candidate the company submits a match query. The company's
   record and the Owner's record meet only inside the sandbox. One bit comes
   back. On ``True`` the company deletes.

The Owner never discloses their data. The company never receives the data it
is being asked to erase.

Two dials, and the reason this module is mostly caveat
------------------------------------------------------

Company records contain typos: ``Wynterbourne`` for ``Winterbourne``,
``12 High St, Flat 3`` for ``Flat 3, 12 High Street``, an address correct in
2019 and stale since. Erasure that only matches exactly is erasure defeated
by the controller's own clerical error -- and defeated *invisibly*, because
"no match" and "not held" are the same answer.

Tolerating that has a price, and it is charged twice:

**The fingerprint dial.** Make it coarse and it survives typos, reveals
little, and admits a large candidate set -- so the company runs many match
queries, each of which is an oracle call. Make it fine and the candidate set
is small and cheap, but a typo'd record never enters it at all, and the
fingerprint itself approaches an identifier. This is DROP's failing: a
deterministic hash of an email address is reversed by hashing candidate
addresses until one matches.

**The threshold dial.** Loose enough to forgive a typo is loose enough to
delete a stranger's record -- unattributably, since nobody involved can tell
it happened. Tight enough to protect the stranger leaves the Owner's record
in place. There is no setting that satisfies both, because the question is
not how similar two strings are but *who bears the cost of the controller's
data-quality failure*. That is an allocation of rights, and this module
declines to make it: see :func:`calibrate_threshold`.

What is implemented here is canonicalisation (:func:`canonicalise_identity`),
which is deterministic, cheap, and closes the *formatting* half of the
problem outright. What is stubbed is the privacy-preserving encoding that
would let genuinely misspelt values match without either side disclosing --
see :func:`encode_for_private_match`. In between sits
:func:`similarity`, a plain edit-distance comparison that makes **no privacy
claim whatsoever**: it exists so the worked example can demonstrate the typo
case end to end, and it operates on plaintext inside the sandbox.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from databank.models import AlgorithmRefusal

#: Bumped whenever canonicalisation changes. Both sides must agree: a
#: Databank canonicalising at v2 against a company still on v1 produces
#: silent non-matches, which look exactly like "we do not hold you".
CANONICALISATION_VERSION = "identity-canon/1"

#: Fixed by the protocol, not by the requestor. See
#: :func:`identity_matches` for why this is not a parameter.
MATCH_THRESHOLD = 0.86

#: Width of the fingerprint band, in bits. Deliberately narrow. See the
#: module docstring on the fingerprint dial.
FINGERPRINT_BITS = 20


class ThresholdNotNegotiable(AlgorithmRefusal):
    """Raised when a requestor tries to choose the match threshold.

    A requestor who can vary the threshold binary-searches the similarity
    score, recovering many bits from a sequence of one-bit answers. The
    threshold is a protocol constant for the same reason the bit budget is.
    """


class CandidateOutsideFingerprint(AlgorithmRefusal):
    """Raised when a submitted candidate is not in the broadcast band.

    Match queries are answerable only for records the fingerprint already
    admits. Without this the query is a general-purpose identity oracle:
    submit any name, learn whether it is the Owner's.
    """


# --------------------------------------------------------------------------
# Canonicalisation -- implemented
# --------------------------------------------------------------------------

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")

#: Apostrophes are *deleted* rather than spaced, so that ``O'Neill`` and
#: ``ONeill`` agree -- both spellings are in real use for the same name, and
#: a form that strips the apostrophe is a formatting variant, not an error.
#: Everything else becomes a space: a hyphen in ``Ferrier-Watson`` separates
#: two names and deleting it would join them.
_APOSTROPHES = re.compile(r"['‘’ʼ´`]")

#: A toy substitution table. A deployment uses a licensed postal address
#: file -- Royal Mail PAF in the UK, USPS AMS in the US -- which is precisely
#: the sort of dependency that makes canonicalisation a governance question
#: rather than a string-handling one: whoever maintains the table decides
#: whose addresses normalise correctly.
_ADDRESS_SUBSTITUTIONS = {
    "st": "street",
    "str": "street",
    "rd": "road",
    "ave": "avenue",
    "av": "avenue",
    "ln": "lane",
    "dr": "drive",
    "ct": "court",
    "pl": "place",
    "sq": "square",
    "cres": "crescent",
    "gdns": "gardens",
    "apt": "flat",
    "apartment": "flat",
    "fl": "flat",
    "no": "",
    "the": "",
}


def _strip_accents(text: str) -> str:
    """Fold accented characters onto their base letters.

    ``Müller`` and ``Muller`` become the same string. ``Mueller`` does not --
    German transliteration is a genuine variant, not a formatting one, and
    belongs to the fuzzy half of the problem.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def canonicalise_name(name: str) -> str:
    """Normalise a personal name for comparison.

    Case, accents, punctuation and spacing are removed. What survives is the
    letter sequence. ``O'Neill``, ``ONeill`` and ``o neill`` agree; ``Bob``
    and ``Robert`` do not, and no canonicalisation will make them -- diminutives
    need a lexicon, and a lexicon that maps ``Bob`` to ``Robert`` will also
    map somebody's legal name to somebody else's.
    """
    folded = _APOSTROPHES.sub("", _strip_accents(name)).casefold()
    folded = _PUNCTUATION.sub(" ", folded)
    return _WHITESPACE.sub(" ", folded).strip()


def canonicalise_address(address: str) -> str:
    """Normalise a street address for comparison.

    Abbreviations are expanded, punctuation dropped, and the tokens sorted so
    that ``Flat 3, 12 High Street`` and ``12 High St, Apt 3`` agree. Sorting
    is a blunt instrument -- it makes ``12 High Street`` and
    ``High Street 12`` agree too, which is right for a Continental address
    format and wrong for a house number that is also a flat number.
    """
    folded = _APOSTROPHES.sub("", _strip_accents(address)).casefold()
    folded = _PUNCTUATION.sub(" ", folded)
    tokens = [
        _ADDRESS_SUBSTITUTIONS.get(token, token) for token in folded.split()
    ]
    return " ".join(sorted(token for token in tokens if token))


def canonicalise_postcode(postcode: str) -> str:
    """Normalise a postcode. ``q12 8ab``, ``Q128AB`` and ``Q12 8AB`` agree."""
    return _PUNCTUATION.sub("", postcode).upper().replace(" ", "")


@dataclass(frozen=True)
class Identity:
    """The identifying data an Owner deposits, as given.

    Held under the attribute ``identity``. Never leaves the sandbox.
    """

    given_name: str
    family_name: str
    address: str
    postcode: str


@dataclass(frozen=True)
class CanonicalIdentity:
    """An :class:`Identity` after :data:`CANONICALISATION_VERSION` folding."""

    given_name: str
    family_name: str
    address: str
    postcode: str
    version: str = CANONICALISATION_VERSION

    def parts(self) -> tuple[str, str, str, str]:
        return (self.given_name, self.family_name, self.address, self.postcode)


def canonicalise_identity(identity: Identity) -> CanonicalIdentity:
    """Fold an identity into its comparable form."""
    return CanonicalIdentity(
        given_name=canonicalise_name(identity.given_name),
        family_name=canonicalise_name(identity.family_name),
        address=canonicalise_address(identity.address),
        postcode=canonicalise_postcode(identity.postcode),
    )


# --------------------------------------------------------------------------
# Fingerprinting -- implemented, deliberately lossy
# --------------------------------------------------------------------------


def _coarse_features(canonical: CanonicalIdentity) -> str:
    """Features chosen to survive a typo, at the cost of being shared.

    The postcode district, the first letter of the family name, and the
    family name's length to the nearest three. A single transposed letter
    inside the surname changes none of them. Neither does a wrong flat
    number. What *does* break the fingerprint is a wrong first letter, a
    wrong postcode district -- a house move -- or a surname misspelt at a
    length boundary. Those records are unreachable by this mechanism, and the
    Owner has no way to learn that they were missed.
    """
    district = re.match(r"[A-Z]{1,2}\d{1,2}[A-Z]?", canonical.postcode)
    family = canonical.family_name
    return "|".join(
        [
            canonical.version,
            district.group(0) if district else "",
            family[:1],
            str(len(family) // 3),
        ]
    )


def fingerprint(
    canonical: CanonicalIdentity, salt: bytes, bits: int = FINGERPRINT_BITS
) -> int:
    """A salted, lossy band identifier -- not an identifier of a person.

    The salt is the Owner's and is published with the erasure broadcast, so
    it does not hide the features from a determined recipient: the feature
    space is small enough to enumerate. Its job is to stop fingerprints from
    being *linkable across broadcasts*, so that receiving companies cannot
    pool their lists into a register of who has asked for erasure. Hiding
    the features themselves is the truncation's job, and the truncation is
    only as good as the number of people sharing the band.
    """
    if not 8 <= bits <= 64:
        raise ValueError("fingerprint width must be between 8 and 64 bits")
    digest = hmac.new(
        salt, _coarse_features(canonical).encode("utf-8"), hashlib.sha256
    ).digest()
    return int.from_bytes(digest[:8], "big") >> (64 - bits)


def select_candidates(
    records: Iterable[CanonicalIdentity],
    band: int,
    salt: bytes,
    bits: int = FINGERPRINT_BITS,
) -> list[CanonicalIdentity]:
    """The company's local narrowing step. Runs on the company's own data.

    No query, no disclosure, no fee: the company is only looking at records
    it already holds. The cost of the erasure falls on the following match
    queries, one per candidate returned here.
    """
    return [r for r in records if fingerprint(r, salt, bits) == band]


# --------------------------------------------------------------------------
# Similarity -- implemented for demonstration, with no privacy claim
# --------------------------------------------------------------------------


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance. Two rows, no dependencies, no subtlety."""
    if a == b:
        return 0
    if not a or not b:
        return len(a) or len(b)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (ca != cb),
                )
            )
        previous = current
    return previous[-1]


def _field_similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    longest = max(len(a), len(b))
    return 1.0 - (_edit_distance(a, b) / longest) if longest else 1.0


#: Relative weight of each canonical field. Surname and postcode carry the
#: match; the given name is the field most often abbreviated, nicknamed or
#: initialised, so it is worth the least.
_FIELD_WEIGHTS = (0.15, 0.35, 0.20, 0.30)


def similarity(a: CanonicalIdentity, b: CanonicalIdentity) -> float:
    """Weighted edit-distance similarity in ``[0, 1]``.

    **This function makes no privacy claim.** It compares plaintext, and is
    safe only because it runs inside the sandbox, where both records are
    already visible to the algorithm and to nothing else. It exists so that
    the worked example can show a real typo being forgiven. A deployment
    cannot use it: the company would have to hand over its record, and the
    whole point is that it does not. That is what
    :func:`encode_for_private_match` is for, and why that one is a stub.
    """
    if a.version != b.version:
        raise ValueError(
            f"canonicalisation mismatch: {a.version!r} vs {b.version!r}; "
            "comparing across versions produces silent non-matches"
        )
    return sum(
        weight * _field_similarity(x, y)
        for weight, x, y in zip(_FIELD_WEIGHTS, a.parts(), b.parts())
    )


def identity_matches(
    identity: Identity,
    candidate: CanonicalIdentity,
    salt: bytes,
    threshold: float | None = None,
) -> bool:
    """Does this company record refer to this Owner? One bit.

    The registered algorithm behind ``identity.matches_owner``. It receives
    the Owner's plaintext identity because it runs inside the sandbox; the
    company receives the return value and nothing else.

    Two refusals are worth reading as design, not validation:

    ``threshold`` **must be left unset.** A requestor free to vary it learns
    the similarity score to arbitrary precision by bisection, and the score
    is a rich function of the underlying strings. One bit per query is only
    one bit if the question is fixed.

    ``candidate`` **must lie in the broadcast band.** Otherwise this is an
    identity oracle: submit any name and postcode, receive a verdict.

    Neither refusal makes the mechanism probe-proof, and it would be
    dishonest to imply otherwise. Within the band, an attacker may still vary
    the fine-grained fields freely and observe where the answer flips,
    recovering the true spelling from the shape of the threshold ball -- in
    exactly the way repeated age-threshold queries binary-search a birth
    year. The band check constrains probing in the coarse dimensions, which
    are the ones a typo does not affect anyway. What actually bounds this
    attack is the Owner's quota, the per-query fee, and the audit trail --
    the same three, and the same open accounting problem, as
    :func:`databank.bitbudget.cumulative_leakage_bound`.
    """
    if threshold is not None:
        raise ThresholdNotNegotiable(
            "the match threshold is fixed by the protocol at "
            f"{MATCH_THRESHOLD}; a requestor-chosen threshold turns a "
            "sequence of one-bit answers into a similarity score"
        )
    canonical = canonicalise_identity(identity)
    if fingerprint(canonical, salt) != fingerprint(candidate, salt):
        raise CandidateOutsideFingerprint(
            "candidate record is not in the broadcast fingerprint band; "
            "match queries are answerable only for records the fingerprint "
            "already admits"
        )
    return similarity(canonical, candidate) >= MATCH_THRESHOLD


# --------------------------------------------------------------------------
# Stubs -- the parts that are not a small job
# --------------------------------------------------------------------------


def encode_for_private_match(canonical: CanonicalIdentity, salt: bytes) -> bytes:
    """Encode an identity so two parties can compare it without revealing it.

    STUB. The standard construction is a Bloom-filter encoding of character
    q-grams compared by Dice coefficient -- Schnell, Bachteler and Reiher's
    privacy-preserving record linkage, which is what a deployment would reach
    for first. It is deliberately not implemented here, because the same
    literature has spent a decade breaking it. Two attack families matter:

    * **Frequency and pattern-mining cryptanalysis.** The encoding preserves
      q-gram frequency, so frequent bit patterns align with frequent
      plaintext values. Christen, Ranbaduge, Vatsalan and Schnell, *Precise
      and Fast Cryptanalysis for Bloom Filter Based PPRL*, IEEE TKDE 31(11),
      2019.
    * **Graph matching.** Build similarity graphs over the encoded and over a
      public plaintext database and align them structurally, which needs far
      less prior knowledge and survives several hardening schemes. Vidanage,
      Christen, Ranbaduge and Schnell, CIKM 2020.

    Both assume the attacker holds a *database* of encodings to align, and
    their success degrades sharply as the overlap between encoded and
    plaintext populations falls. That is the one structural comfort available
    here, and it decays: a broker receiving erasure broadcasts accumulates
    encodings over time, and the population it accumulates is precisely the
    one that asked to be forgotten. An encoding safe against a single
    broadcast is not thereby safe against a year of them.

    Implementing an encoding that *looks* private and is not would be the
    worst outcome available to this repository, since the whole erasure case
    rests on the claim that the fingerprint is not a register. Either this
    lands with a citation and a threat model, or it stays a stub.
    """
    raise NotImplementedError(
        "privacy-preserving identity encoding is not implemented; see the "
        "Technical Architecture Paper"
    )


def private_match(
    owner_encoding: bytes, candidate_encoding: bytes, threshold: float
) -> bool:
    """Compare two encodings without either party learning the other's input.

    STUB. Needs a two-party protocol -- threshold private set intersection,
    or a garbled circuit over the Dice coefficient -- with the threshold
    baked into the circuit rather than supplied at call time. The performance
    question is not incidental: an erasure broadcast to six hundred brokers,
    each holding several candidate records, is thousands of two-party
    protocol runs for one Owner exercising one right.
    """
    raise NotImplementedError("two-party private matching is not implemented")


def calibrate_threshold(false_positive_cost: float, false_negative_cost: float) -> float:
    """Choose the match threshold.

    STUB, and not for want of a formula. The two errors fall on different
    people. A false negative leaves the Owner's record in place because the
    controller mistyped it, and neither party can detect the failure. A false
    positive destroys a third party's record -- someone who asked for
    nothing, is never told, and has no obvious remedy, since the erasure
    obligation runs to the requester and the accuracy obligation runs to the
    controller, and this harm sits between them.

    There is an argument that the threshold should be set loose, and it is a
    legal argument rather than a statistical one: the typo is the
    controller's, and a controller who cannot reliably identify which record
    is whose has trouble demonstrating either the accuracy required by GDPR
    Art. 5(1)(d) or the accountability required by Art. 5(2). On that reading
    ambiguity resolves toward erasure and the controller bears the cost of
    its own data quality. That is a position the whitepaper can take. It is
    not one a function signature should take by returning a number.
    """
    raise NotImplementedError(
        "the match threshold allocates the cost of a controller's data-quality "
        "failure between the Owner and an uninvolved third party; it is a "
        "policy choice, not a calibration"
    )


def erasure_receipt(owner_id: str, requestor_id: str, matched: bool) -> bytes:
    """Evidence that a company answered an erasure request, and how.

    STUB. The Databank can log that a match query was asked and answered; it
    cannot see whether the company then deleted anything. Closing that gap
    needs the company to attest to the deletion in a way the Owner can hold
    -- and an attestation the company generates about its own systems is
    worth what the penalty for lying about it is worth. Under California's
    Delete Act that is $200 per request per day. Enforcement is statutory
    here as everywhere else; the protocol's contribution ends at not leaking
    the data on the way in.
    """
    raise NotImplementedError("deletion receipts are not implemented")
