"""Bit accounting for query outputs.

The whitepaper's *bit-scarce* property: an output is intentionally
constrained to reveal only a small amount of information relative to the
underlying record, capped in practice at three to four bits.

What this module does: measure the information content of a single response
and reject anything over the cap.

What it does not do: bound *cumulative* leakage across repeated queries. A
requestor who runs threshold checks at 18, 19, 20... can binary-search a
birth year while every individual response stays within a one-bit cap. That
is bounded by :mod:`databank.leakage`: a per-datum quota, shared by all
requestors and derived from the retention limit on what a requestor may
hold. What remains open is an *estimate* of the information actually
disclosed by a given sequence; see :func:`cumulative_leakage_bound`.
"""

from __future__ import annotations

import math
from typing import Any

#: Default per-response ceiling, in bits.
DEFAULT_MAX_BITS = 4


class BitBudgetExceeded(RuntimeError):
    """Raised when a response would disclose more than the cap allows."""


def measure_bits(value: Any) -> int:
    """Return the information content of ``value`` in bits.

    Booleans are one bit. A value drawn from a known finite set of ``n``
    admissible outcomes is ``ceil(log2(n))`` bits. Anything whose domain the
    Databank cannot bound is refused outright rather than guessed at -- an
    unbounded response is exactly the leak the model exists to prevent.
    """
    if isinstance(value, bool):
        return 1
    if isinstance(value, EnumeratedOutcome):
        return max(1, math.ceil(math.log2(value.domain_size)))
    raise BitBudgetExceeded(
        f"cannot bound the information content of {type(value).__name__}; "
        "responses must be booleans or EnumeratedOutcome instances"
    )


class EnumeratedOutcome:
    """A response drawn from an explicitly bounded set of outcomes.

    Example: a five-year age bracket, where ``domain_size`` is the number of
    brackets the algorithm may ever return.
    """

    __slots__ = ("value", "domain_size")

    def __init__(self, value: Any, domain_size: int) -> None:
        if domain_size < 2:
            raise ValueError("domain_size must be at least 2")
        self.value = value
        self.domain_size = domain_size

    def __eq__(self, other: object) -> bool:
        if isinstance(other, EnumeratedOutcome):
            return (self.value, self.domain_size) == (other.value, other.domain_size)
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.value, self.domain_size))

    def __repr__(self) -> str:
        return f"EnumeratedOutcome({self.value!r}, domain_size={self.domain_size})"


def enforce(value: Any, max_bits: int = DEFAULT_MAX_BITS) -> int:
    """Measure ``value`` and raise if it exceeds ``max_bits``."""
    bits = measure_bits(value)
    if bits > max_bits:
        raise BitBudgetExceeded(
            f"response discloses {bits} bits, cap is {max_bits}"
        )
    return bits


def cumulative_leakage_bound(audit_entries, attribute: str) -> float:
    """Estimate total bits leaked about ``attribute`` across many queries.

    STUB. The *bound* is enforced by :class:`databank.leakage.LeakageBudget`,
    which caps how many answers about a datum can be held at once. This
    function would be the complementary *estimate*: how much a particular
    sequence in the audit log actually disclosed, for a regulator or an
    owner reviewing it after the fact. Naively summing per-response bits
    overstates leakage for repeated identical queries and understates it for
    adaptively chosen thresholds, which is why this needs a proper treatment
    rather than a plausible-looking sum.
    """
    raise NotImplementedError(
        "estimating disclosed information from an audit sequence is open "
        "work; the leakage bound itself is enforced by databank.leakage"
    )
