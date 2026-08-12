"""The algorithm registry.

Requestors do not send queries; they send algorithms drawn from a registry
the Databank can inspect, reason about, and cap. Registration records the
attribute an algorithm reads and the maximum number of bits it may return,
so the permission check can be made before any plaintext is touched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable


@dataclass(frozen=True)
class Algorithm:
    """A registered, inspectable computation."""

    id: str
    fn: Callable[..., Any]
    attribute: str
    max_output_bits: int
    description: str


_REGISTRY: dict[str, Algorithm] = {}


def register(
    algorithm_id: str, attribute: str, max_output_bits: int, description: str
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator registering an algorithm under ``algorithm_id``."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if algorithm_id in _REGISTRY:
            raise ValueError(f"algorithm {algorithm_id!r} already registered")
        _REGISTRY[algorithm_id] = Algorithm(
            id=algorithm_id,
            fn=fn,
            attribute=attribute,
            max_output_bits=max_output_bits,
            description=description,
        )
        return fn

    return decorator


def get(algorithm_id: str) -> Algorithm:
    try:
        return _REGISTRY[algorithm_id]
    except KeyError:
        raise KeyError(f"no algorithm registered as {algorithm_id!r}") from None


def registered() -> list[str]:
    return sorted(_REGISTRY)


# --------------------------------------------------------------------------
# Implemented
# --------------------------------------------------------------------------


def _years_between(start: date, end: date) -> int:
    """Whole years elapsed, without pulling in a date library."""
    years = end.year - start.year
    if (end.month, end.day) < (start.month, start.day):
        years -= 1
    return years


@register(
    "age.over_threshold",
    attribute="date_of_birth",
    max_output_bits=1,
    description="Is the owner at least N years old as of a given date?",
)
def age_over_threshold(
    date_of_birth: date, threshold_years: int, as_of: date
) -> bool:
    """Return whether the owner has reached ``threshold_years``.

    The date of birth is visible only here, inside the sandbox. Exactly one
    bit leaves: no date, no exact age, no margin.
    """
    return _years_between(date_of_birth, as_of) >= threshold_years


# --------------------------------------------------------------------------
# Stubs -- registered so the shape is visible, not yet implemented
# --------------------------------------------------------------------------


@register(
    "income.over_threshold",
    attribute="annual_income",
    max_output_bits=1,
    description="Does the owner's income clear a stated threshold?",
)
def income_over_threshold(annual_income: Any, threshold: Any) -> bool:
    """STUB. Needs a currency and reference-period model before it means
    anything; a bare numeric comparison would silently compare across
    currencies and tax years."""
    raise NotImplementedError("income.over_threshold is not implemented")


@register(
    "location.within_region",
    attribute="home_address",
    max_output_bits=1,
    description="Is the owner's address inside a stated administrative region?",
)
def location_within_region(home_address: Any, region_code: str) -> bool:
    """STUB. Requires a geocoding boundary set inside the sandbox. Note that
    repeated queries over shrinking regions binary-search an address, so this
    one should not ship before cumulative-leakage accounting exists."""
    raise NotImplementedError("location.within_region is not implemented")


@register(
    "health.flag_present",
    attribute="health_record",
    max_output_bits=1,
    description="Is a specified clinical flag present in the owner's record?",
)
def health_flag_present(health_record: Any, flag: str) -> bool:
    """STUB. Special-category data under UK/EU law: needs an explicit lawful
    basis and a narrower consent model than standing permissions provide."""
    raise NotImplementedError("health.flag_present is not implemented")
