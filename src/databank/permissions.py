"""Permission checking.

Every query meets the owner's standing permissions before it meets any data.
Three outcomes: admit, reject outright, or forward a one-off consent request
to the owner. The default for an unrecognised request is *not* rejection but
consent -- rejecting silently would deny the owner the chance to say yes.
"""

from __future__ import annotations

from collections import defaultdict

from databank.models import Decision, Query, StandingPermission


class PermissionLedger:
    """Standing permissions plus the usage counters that enforce quotas."""

    def __init__(self) -> None:
        self._grants: list[StandingPermission] = []
        self._usage: dict[tuple[str, str, str, int], int] = defaultdict(int)

    def grant(self, permission: StandingPermission) -> None:
        self._grants.append(permission)

    def revoke(self, requestor_id: str, algorithm_id: str) -> int:
        """Withdraw matching grants. Returns how many were removed."""
        before = len(self._grants)
        self._grants = [
            g
            for g in self._grants
            if not (g.requestor_id == requestor_id and g.algorithm_id == algorithm_id)
        ]
        return before - len(self._grants)

    def _matching(self, query: Query) -> StandingPermission | None:
        for grant in self._grants:
            if (
                grant.requestor_id == query.requestor_id
                and grant.algorithm_id == query.algorithm_id
                and grant.attribute == query.attribute
            ):
                return grant
        return None

    def check(self, query: Query, year: int) -> tuple[Decision, str | None]:
        """Decide on ``query``, without consuming quota."""
        grant = self._matching(query)
        if grant is None:
            return (
                Decision.CONSENT_REQUIRED,
                "no standing permission covers this requestor and algorithm",
            )
        if grant.quota_per_year is not None:
            key = (
                query.requestor_id,
                query.algorithm_id,
                query.attribute,
                year,
            )
            if self._usage[key] >= grant.quota_per_year:
                return (
                    Decision.DENY,
                    f"annual quota of {grant.quota_per_year} exhausted for {year}",
                )
        return Decision.ALLOW, None

    def consume(self, query: Query, year: int) -> None:
        """Record one use against the quota. Call only after execution."""
        key = (query.requestor_id, query.algorithm_id, query.attribute, year)
        self._usage[key] += 1

    def usage(self, query: Query, year: int) -> int:
        return self._usage[
            (query.requestor_id, query.algorithm_id, query.attribute, year)
        ]
