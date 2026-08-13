"""Databanking reference implementation.

A minimal, dependency-free model of the query flow described in the
Databanking whitepaper: an Information Requestor submits an *algorithm* to an
Information Owner's Databank, the algorithm executes inside a sandbox against
data the requestor never sees, and a deliberately tiny answer -- often a
single bit -- crosses the boundary, logged on the owner's statement.

This is a reference model for discussion and review, not production software.
See https://databanking.org.
"""

from databank.databank import Databank
from databank.matching import (
    CanonicalIdentity,
    Identity,
    canonicalise_identity,
    fingerprint,
    select_candidates,
)
from databank.models import (
    AuditEntry,
    Decision,
    Query,
    QueryResult,
    Record,
    StandingPermission,
)

__version__ = "0.1.0"

__all__ = [
    "AuditEntry",
    "CanonicalIdentity",
    "Databank",
    "Decision",
    "Identity",
    "Query",
    "QueryResult",
    "Record",
    "StandingPermission",
    "__version__",
    "canonicalise_identity",
    "fingerprint",
    "select_candidates",
]
