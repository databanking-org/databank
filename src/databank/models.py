"""Core value types for the Databank reference implementation.

The vocabulary here follows the Databanking whitepaper:

* **Information Owner** -- the natural person whose data is held.
* **Information Requestor** -- the party submitting an algorithm.
* **Databank** -- the custodian that holds the record and runs the sandbox.

Nothing in this module performs cryptography. ``SealedValue`` models the
*boundary*, not the protection: in a real deployment the payload is sealed to
a hardware enclave and is never readable by the Databank's own operators. The
point of modelling it as a distinct type is that unsealing requires a
``SandboxContext``, so any code path that tries to read a plaintext outside
the sandbox is a type error rather than a judgement call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any


class Decision(str, Enum):
    """Outcome of the Databank's permission check on an incoming query."""

    ALLOW = "allow"
    DENY = "deny"
    CONSENT_REQUIRED = "consent_required"


class SealError(RuntimeError):
    """Raised when a sealed value is read outside a sandbox context."""


@dataclass(frozen=True)
class SealedValue:
    """A stored attribute value that only the sandbox may read.

    Access is deliberately awkward: :meth:`unseal` demands a live
    ``SandboxContext``. See :mod:`databank.sandbox`.
    """

    _payload: Any

    def unseal(self, context: Any) -> Any:
        # Imported lazily to keep the module dependency-free at import time.
        from databank.sandbox import SandboxContext

        if not isinstance(context, SandboxContext) or not context.active:
            raise SealError(
                "sealed values may only be read inside an active sandbox context"
            )
        return self._payload

    def __repr__(self) -> str:  # pragma: no cover - defensive
        return "SealedValue(<sealed>)"


@dataclass(frozen=True)
class Record:
    """One attribute deposited by an Information Owner."""

    owner_id: str
    attribute: str
    value: SealedValue
    deposited_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(frozen=True)
class StandingPermission:
    """A pre-authorisation granted by the owner.

    ``quota_per_year`` implements the whitepaper's example of "age-threshold
    checks from verified retailers, twice per requestor per year". A quota of
    ``None`` means unlimited within the grant.
    """

    requestor_id: str
    algorithm_id: str
    attribute: str
    quota_per_year: int | None = None


@dataclass(frozen=True)
class Query:
    """An algorithm submitted by a requestor -- not a request for data."""

    requestor_id: str
    owner_id: str
    algorithm_id: str
    attribute: str
    parameters: dict[str, Any] = field(default_factory=dict)
    as_of: date | None = None


@dataclass(frozen=True)
class QueryResult:
    """What crosses the boundary back to the requestor."""

    decision: Decision
    value: Any = None
    bits_disclosed: int = 0
    reason: str | None = None

    @property
    def executed(self) -> bool:
        return self.decision is Decision.ALLOW


@dataclass(frozen=True)
class AuditEntry:
    """One line on the owner's statement.

    Every query is logged, including denied and consent-pending ones: the
    audit trail is what makes repeated-query probing visible to the owner.
    """

    timestamp: datetime
    owner_id: str
    requestor_id: str
    algorithm_id: str
    attribute: str
    decision: Decision
    bits_disclosed: int
    reason: str | None = None
