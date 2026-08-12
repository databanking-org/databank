"""Unimplemented surfaces must fail loudly, not plausibly.

A stub that silently returns a default is worse than no stub at all: it
invites someone to build on a number nobody chose.
"""

import pytest

from databank import algorithms
from databank.attestation import measurement_of, verify_quote
from databank.audit import AuditLog, seal_chain
from databank.settlement import access_fee, owner_share
from databank.storage import RecordStore, persist


def test_settlement_is_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        access_fee(None, 1)
    with pytest.raises(NotImplementedError):
        owner_share(1.0, "UK")


def test_attestation_is_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        verify_quote(b"", b"")
    with pytest.raises(NotImplementedError):
        measurement_of(None)


def test_audit_sealing_is_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        seal_chain(AuditLog())


def test_persistence_is_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        persist(RecordStore(), "/tmp/nowhere")


@pytest.mark.parametrize(
    "algorithm_id",
    ["income.over_threshold", "location.within_region", "health.flag_present"],
)
def test_stubbed_algorithms_are_registered_but_unimplemented(algorithm_id: str) -> None:
    algorithm = algorithms.get(algorithm_id)
    assert algorithm.max_output_bits <= 4
    with pytest.raises(NotImplementedError):
        algorithm.fn(None, None)


def test_registry_lists_every_algorithm() -> None:
    assert "age.over_threshold" in algorithms.registered()
    with pytest.raises(KeyError):
        algorithms.get("no.such.algorithm")
