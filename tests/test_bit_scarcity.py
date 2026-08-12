from datetime import date

import pytest

from databank.bitbudget import (
    BitBudgetExceeded,
    EnumeratedOutcome,
    cumulative_leakage_bound,
    enforce,
    measure_bits,
)
from databank.models import Record, SealError, SealedValue
from databank.sandbox import execute, sandbox, seal


def test_boolean_is_one_bit() -> None:
    assert measure_bits(True) == 1
    assert measure_bits(False) == 1


def test_five_year_brackets_are_about_four_bits() -> None:
    # ~20 brackets spanning a human lifespan
    assert measure_bits(EnumeratedOutcome("40-44", domain_size=20)) == 5
    assert measure_bits(EnumeratedOutcome("40-44", domain_size=16)) == 4


def test_unbounded_values_are_refused_outright() -> None:
    with pytest.raises(BitBudgetExceeded):
        measure_bits(date(2007, 4, 2))
    with pytest.raises(BitBudgetExceeded):
        measure_bits("1990-01-01")
    with pytest.raises(BitBudgetExceeded):
        measure_bits(37)


def test_cap_is_enforced() -> None:
    assert enforce(True, max_bits=1) == 1
    with pytest.raises(BitBudgetExceeded):
        enforce(EnumeratedOutcome("x", domain_size=64), max_bits=4)


def test_over_budget_result_never_leaves_the_sandbox() -> None:
    record = Record("alice", "date_of_birth", seal(date(2007, 4, 2)))

    def leaky(date_of_birth):
        return date_of_birth  # tries to return the record itself

    with pytest.raises(BitBudgetExceeded):
        execute(leaky, "leaky", record, max_bits=1)


def test_sealed_value_is_unreadable_outside_a_sandbox() -> None:
    sealed = seal(date(2007, 4, 2))
    with pytest.raises(SealError):
        sealed.unseal(None)
    with pytest.raises(SealError):
        sealed.unseal(object())


def test_sealed_value_repr_does_not_leak() -> None:
    assert "2007" not in repr(seal(date(2007, 4, 2)))
    assert "sealed" in repr(SealedValue("secret")).lower()


def test_context_is_revoked_after_execution() -> None:
    sealed = seal("secret")
    with sandbox("probe") as context:
        assert sealed.unseal(context) == "secret"
    with pytest.raises(SealError):
        sealed.unseal(context)


def test_cumulative_leakage_is_explicitly_open_work() -> None:
    with pytest.raises(NotImplementedError, match="Technical"):
        cumulative_leakage_bound([], "date_of_birth")
