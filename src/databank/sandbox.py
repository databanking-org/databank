"""The execution boundary.

An admitted algorithm runs here, against the unsealed record, and returns a
bit-scarce result. The requestor never sees inside; the Databank never hands
out the plaintext.

This module is a *model* of that boundary, not an enforcement of it: real
isolation comes from a hardware enclave or an equivalent confidential
computing primitive, whose attestation is stubbed in
:mod:`databank.attestation`. What is faithfully modelled here is the shape of
the contract -- plaintext is reachable only within an active context, and
only the measured return value leaves it.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator

from databank.bitbudget import enforce
from databank.models import Record, SealedValue


class SandboxContext:
    """Capability token proving that code is executing inside the sandbox."""

    __slots__ = ("active", "algorithm_id")

    def __init__(self, algorithm_id: str) -> None:
        self.algorithm_id = algorithm_id
        self.active = False


@contextmanager
def sandbox(algorithm_id: str) -> Iterator[SandboxContext]:
    """Enter a sandbox context for ``algorithm_id``."""
    context = SandboxContext(algorithm_id)
    context.active = True
    try:
        yield context
    finally:
        # Revoking the token means any reference the algorithm squirrelled
        # away is useless once execution ends.
        context.active = False


def execute(
    algorithm: Callable[..., Any],
    algorithm_id: str,
    record: Record,
    max_bits: int,
    **parameters: Any,
) -> tuple[Any, int]:
    """Run ``algorithm`` against ``record`` inside a sandbox.

    Returns the result together with the number of bits it discloses. Raises
    :class:`databank.bitbudget.BitBudgetExceeded` if the algorithm tries to
    return more than ``max_bits``, in which case nothing crosses the boundary.
    """
    with sandbox(algorithm_id) as context:
        plaintext = record.value.unseal(context)
        result = algorithm(plaintext, **parameters)
        # Measured inside the boundary: an over-budget result is discarded
        # here rather than returned and regretted later.
        bits = enforce(result, max_bits)
    return result, bits


def seal(value: Any) -> SealedValue:
    """Seal a plaintext value for deposit.

    In deployment this is an enclave sealing operation bound to the owner's
    key. Here it is a wrapper whose only job is to make unsealing explicit.
    """
    return SealedValue(value)
