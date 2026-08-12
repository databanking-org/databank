"""The Databank itself: deposit, permission, sandbox, audit.

The whole flow in one place. Follow :meth:`Databank.submit_query` to see the
five steps of the worked example at https://databanking.org/worked-example.html.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from databank import algorithms
from databank.audit import AuditLog
from databank.models import (
    Decision,
    Query,
    QueryResult,
    Record,
    StandingPermission,
)
from databank.permissions import PermissionLedger
from databank.sandbox import execute, seal
from databank.storage import RecordStore


class Databank:
    """A custodian holding records on behalf of Information Owners."""

    def __init__(self, name: str = "reference-databank") -> None:
        self.name = name
        self._records = RecordStore()
        self._permissions: dict[str, PermissionLedger] = {}
        self.audit = AuditLog()

    # -- owner-facing ------------------------------------------------------

    def deposit(self, owner_id: str, attribute: str, value: Any) -> Record:
        """Deposit an attribute. The value is sealed on the way in."""
        record = Record(owner_id=owner_id, attribute=attribute, value=seal(value))
        self._records.put(record)
        return record

    def grant(
        self,
        owner_id: str,
        requestor_id: str,
        algorithm_id: str,
        attribute: str,
        quota_per_year: int | None = None,
    ) -> StandingPermission:
        """Pre-authorise a requestor to run one algorithm on one attribute."""
        algorithms.get(algorithm_id)  # fail fast on unknown algorithms
        permission = StandingPermission(
            requestor_id=requestor_id,
            algorithm_id=algorithm_id,
            attribute=attribute,
            quota_per_year=quota_per_year,
        )
        self._ledger(owner_id).grant(permission)
        return permission

    def revoke(self, owner_id: str, requestor_id: str, algorithm_id: str) -> int:
        return self._ledger(owner_id).revoke(requestor_id, algorithm_id)

    def statement(self, owner_id: str):
        """The owner's transaction statement: every query touching them."""
        return self.audit.entries(owner_id)

    def erase(self, owner_id: str, attribute: str) -> bool:
        """Erase an attribute. The audit trail of past queries is retained.

        Deleting the record does not rewrite history: the owner keeps the
        evidence of who asked what, which is the thing they would actually
        need in a dispute.
        """
        return self._records.erase(owner_id, attribute)

    # -- requestor-facing --------------------------------------------------

    def submit_query(self, query: Query) -> QueryResult:
        """Submit an algorithm and receive a bit-scarce answer.

        1. Look up the registered algorithm (no data touched yet).
        2. Check the owner's standing permissions.
        3. Execute inside the sandbox, where the algorithm alone meets the
           sealed record.
        4. Return at most the algorithm's declared bit budget.
        5. Log the transaction on the owner's statement.
        """
        algorithm = algorithms.get(query.algorithm_id)

        if algorithm.attribute != query.attribute:
            result = QueryResult(
                Decision.DENY,
                reason=(
                    f"algorithm {algorithm.id!r} reads {algorithm.attribute!r}, "
                    f"not {query.attribute!r}"
                ),
            )
            self.audit.record(query, result.decision, 0, result.reason)
            return result

        year = (query.as_of or date.today()).year
        decision, reason = self._ledger(query.owner_id).check(query, year)

        if decision is not Decision.ALLOW:
            self.audit.record(query, decision, 0, reason)
            return QueryResult(decision, reason=reason)

        record = self._records.get(query.owner_id, query.attribute)
        if record is None:
            reason = f"no record held for attribute {query.attribute!r}"
            self.audit.record(query, Decision.DENY, 0, reason)
            return QueryResult(Decision.DENY, reason=reason)

        value, bits = execute(
            algorithm.fn,
            algorithm.id,
            record,
            algorithm.max_output_bits,
            **query.parameters,
        )

        self._ledger(query.owner_id).consume(query, year)
        self.audit.record(query, Decision.ALLOW, bits)
        return QueryResult(Decision.ALLOW, value=value, bits_disclosed=bits)

    # -- internals ---------------------------------------------------------

    def _ledger(self, owner_id: str) -> PermissionLedger:
        return self._permissions.setdefault(owner_id, PermissionLedger())
