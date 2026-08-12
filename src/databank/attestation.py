"""Enclave attestation.

Before depositing anything, an owner should be able to verify that the
Databank's sandbox really is what it claims to be, and before submitting an
algorithm a requestor should be able to verify the same. Without this the
whole model rests on trusting the Databank's word, which is the trust
relationship it exists to remove.
"""

from __future__ import annotations

from typing import Any


def verify_quote(quote: bytes, expected_measurement: bytes) -> bool:
    """Verify a remote attestation quote against an expected measurement.

    STUB. Vendor-specific (SGX/TDX/SEV-SNP each differ), and binding the
    quote to a published, reproducible build of the sandbox matters more than
    the signature check itself -- an attested enclave running unaudited code
    proves very little.
    """
    raise NotImplementedError("attestation verification is not implemented")


def measurement_of(sandbox_build: Any) -> bytes:
    """Compute the expected measurement of a sandbox build.

    STUB. Requires a reproducible build pipeline.
    """
    raise NotImplementedError("build measurement is not implemented")
