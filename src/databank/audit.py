"""The owner's statement.

Every query is logged -- admitted, denied, or pending consent. The audit
trail is not a compliance afterthought: together with quotas it is what
closes the repeated-query probing gap that bit-scarcity alone leaves open.
"""

from __future__ import annotations

from datetime import datetime, timezone

from databank.models import AuditEntry, Decision, Query


class AuditLog:
    """In-memory append-only log.

    Deployment needs tamper-evidence -- a hash chain or transparency log --
    so that a Databank cannot quietly drop entries it finds inconvenient.
    See :func:`seal_chain`.
    """

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def record(
        self,
        query: Query,
        decision: Decision,
        bits_disclosed: int,
        reason: str | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc),
            owner_id=query.owner_id,
            requestor_id=query.requestor_id,
            algorithm_id=query.algorithm_id,
            attribute=query.attribute,
            decision=decision,
            bits_disclosed=bits_disclosed,
            reason=reason,
        )
        self._entries.append(entry)
        return entry

    def entries(self, owner_id: str | None = None) -> list[AuditEntry]:
        if owner_id is None:
            return list(self._entries)
        return [e for e in self._entries if e.owner_id == owner_id]

    def __len__(self) -> int:
        return len(self._entries)


def seal_chain(log: AuditLog) -> bytes:
    """Produce a tamper-evident commitment over the log.

    STUB. A plain hash chain is easy and insufficient on its own: it lets an
    owner detect tampering only if they retained an earlier root, so this
    needs either owner-held checkpoints or a third-party transparency log.
    Deferred to the Technical Architecture Paper.
    """
    raise NotImplementedError("tamper-evident audit sealing is not implemented")
