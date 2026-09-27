"""Retention-bounded leakage budget.

Bit-scarcity caps what a single response discloses. It does not, on its own,
stop a requestor from asking many one-bit questions and combining the
answers: threshold checks at 18, 19, 20... binary-search a birth year, and
the same check evaluated on successive dates binary-searches the birthday.

The Databanking model closes that gap through four of its properties:

1. Only a Databank may lawfully store attributable personal data.
2. Only attested requestors may query, and every query is logged against
   the requestor's attested identity, so query capacity cannot be
   multiplied by multiplying anonymous clients.
3. A requestor may hold a result only for a short retention period ``tau``,
   long enough to reach the decision the query was approved for. The
   decision itself falls under the same rule.
4. Narrowing a datum by repeated queries requires the intermediate results
   to be combined, and therefore held.

A compliant requestor can therefore hold, at any moment, only the results of
queries issued within the preceding ``tau``. If a datum takes one of ``R``
distinguishable values under a realistic prior and must not be resolved more
finely than ``r``, an adaptive adversary needs about
``k = ceil(log2(R / r))`` binary answers. Allowing fewer than ``k`` queries
in any window of length ``tau`` bounds what can be held at any time, and
defines a maximum request frequency ``f_max = n_tau / tau``.

A daily quota, set well below what the per-``tau`` bound alone would allow,
supplies the margin: a requestor that breaks the retention rule is slowed to
the daily quota and leaves a range-halving query sequence in the audit log.
The retention rule makes the attack unlawful; the quota and the log make it
slow and evidenced.

Unlike a differential-privacy budget, which is spent over the lifetime of a
dataset, this budget renews: what a requestor may hold expires after
``tau``, and the quota is replenished at the same rate.

Structure, as specified in the Technical Architecture Paper (section "A
retention-bounded leakage budget"):

* the quota attaches to the datum, not to the requestor, and counts queries
  from all requestors together, so collusion gains no additional queries;
* correlated attributes (date of birth, age, school year...) are grouped and
  share one quota;
* each requestor's share is smaller than the daily per-datum quota, so no
  single requestor can exhaust the quota and deny legitimate checks to
  others;
* ``R`` is set by the realistic prior for the datum, not the full range of
  the field, and differs between, for instance, an adult and a child;
* designated requestors may be exempt from the quota, with their queries
  recorded in the log in the ordinary way.

The parameter values here are illustrative. Choosing them -- ``tau`` per
query class, the attribute groupings, the prior ranges, the per-requestor
share, the scope of exemptions -- is open work.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from databank.models import Decision

#: The window over which the daily quota and the per-requestor share apply.
DAY = timedelta(days=1)


def answers_to_resolve(prior_range: float, resolution: float) -> int:
    """Binary answers an adaptive adversary needs to narrow a datum.

    ``prior_range`` and ``resolution`` are in the same unit (days, say):
    the width of the realistic prior, and the finest resolution the datum
    may be resolved to. Returns ``ceil(log2(prior_range / resolution))``,
    at least 1.
    """
    if prior_range <= 0 or resolution <= 0:
        raise ValueError("prior_range and resolution must be positive")
    if resolution >= prior_range:
        return 1
    return max(1, math.ceil(math.log2(prior_range / resolution)))


@dataclass(frozen=True)
class DatumPolicy:
    """The leakage budget for one group of correlated attributes.

    ``per_window`` is derived, not chosen: the largest number of queries in
    any interval of length ``tau`` that stays below the ``k`` answers needed
    to reach ``resolution``. A policy whose daily quota would allow more
    than that inside one retention window is still valid -- the tighter of
    the two limits applies -- but a per-requestor share that is not smaller
    than the daily quota is rejected, because it would let one requestor
    exhaust the datum for everyone.
    """

    group: str
    attributes: frozenset[str]
    tau: timedelta
    daily_quota: int
    requestor_share: int
    prior_range: float
    resolution: float
    exempt_requestors: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.attributes:
            raise ValueError("a policy must cover at least one attribute")
        if self.tau <= timedelta(0):
            raise ValueError("tau must be positive; tau = 0 is not achievable")
        if self.tau > DAY:
            raise ValueError("tau longer than a day defeats the daily quota")
        if self.daily_quota < 1:
            raise ValueError("daily_quota must be at least 1")
        if not 1 <= self.requestor_share < self.daily_quota:
            raise ValueError(
                "requestor_share must be at least 1 and smaller than "
                "daily_quota, so no single requestor can exhaust the datum"
            )
        if self.per_window < 1:
            raise ValueError(
                "prior_range / resolution admits no query at all; widen the "
                "resolution or drop the policy"
            )

    @property
    def answers_to_resolve(self) -> int:
        """``k``: binary answers needed to resolve the datum to ``resolution``."""
        return answers_to_resolve(self.prior_range, self.resolution)

    @property
    def per_window(self) -> int:
        """``n_tau``: queries allowed in any window of length ``tau``."""
        return self.answers_to_resolve - 1

    @property
    def max_request_frequency(self) -> float:
        """``f_max = n_tau / tau``, in queries per second."""
        return self.per_window / self.tau.total_seconds()


@dataclass(frozen=True)
class _Use:
    at: datetime
    requestor_id: str
    exempt: bool


class LeakageBudget:
    """Enforces :class:`DatumPolicy` limits for every owner at a Databank.

    Because a category of an owner's data is held by exactly one custodian,
    the quota for any datum is enforced in one place: here.

    Usage mirrors :class:`databank.permissions.PermissionLedger`: call
    :meth:`check` before execution and :meth:`consume` after it, so that a
    denied query never counts against the budget.
    """

    def __init__(self, policies: list[DatumPolicy] | None = None) -> None:
        self._policies: dict[str, DatumPolicy] = {}
        self._group_of: dict[str, str] = {}
        self._uses: dict[tuple[str, str], deque[_Use]] = defaultdict(deque)
        for policy in policies or []:
            self.add(policy)

    def add(self, policy: DatumPolicy) -> None:
        """Register a policy. An attribute may belong to one group only."""
        if policy.group in self._policies:
            raise ValueError(f"group {policy.group!r} already has a policy")
        for attribute in policy.attributes:
            if attribute in self._group_of:
                raise ValueError(
                    f"attribute {attribute!r} already belongs to group "
                    f"{self._group_of[attribute]!r}"
                )
        self._policies[policy.group] = policy
        for attribute in policy.attributes:
            self._group_of[attribute] = policy.group

    def policy_for(self, attribute: str) -> DatumPolicy | None:
        group = self._group_of.get(attribute)
        return self._policies[group] if group is not None else None

    def check(
        self, owner_id: str, requestor_id: str, attribute: str, at: datetime
    ) -> tuple[Decision, str | None]:
        """Decide whether a query may run, without consuming budget.

        Attributes outside every policy are not governed here and are
        admitted; the permission ledger still applies to them.
        """
        policy = self.policy_for(attribute)
        if policy is None or requestor_id in policy.exempt_requestors:
            return Decision.ALLOW, None

        uses = self._recent(owner_id, policy, at)
        counted = [u for u in uses if not u.exempt]

        in_window = sum(1 for u in counted if u.at > at - policy.tau)
        if in_window >= policy.per_window:
            return Decision.DENY, (
                f"retention-window limit reached for {policy.group!r}: "
                f"{policy.per_window} queries per {_fmt(policy.tau)}"
            )
        if len(counted) >= policy.daily_quota:
            return Decision.DENY, (
                f"daily quota of {policy.daily_quota} exhausted for "
                f"{policy.group!r}"
            )
        own = sum(1 for u in counted if u.requestor_id == requestor_id)
        if own >= policy.requestor_share:
            return Decision.DENY, (
                f"requestor share of {policy.requestor_share} per day "
                f"exhausted for {policy.group!r}"
            )
        return Decision.ALLOW, None

    def consume(
        self, owner_id: str, requestor_id: str, attribute: str, at: datetime
    ) -> None:
        """Record one executed query. Exempt requestors are recorded too,
        but do not count against the quota."""
        policy = self.policy_for(attribute)
        if policy is None:
            return
        self._uses[(owner_id, policy.group)].append(
            _Use(at, requestor_id, requestor_id in policy.exempt_requestors)
        )

    def remaining(
        self, owner_id: str, attribute: str, at: datetime
    ) -> int | None:
        """Queries left today on this owner's datum, across all requestors."""
        policy = self.policy_for(attribute)
        if policy is None:
            return None
        used = sum(1 for u in self._recent(owner_id, policy, at) if not u.exempt)
        return max(0, policy.daily_quota - used)

    def _recent(
        self, owner_id: str, policy: DatumPolicy, at: datetime
    ) -> list[_Use]:
        """Uses within the last day, pruning anything older."""
        uses = self._uses[(owner_id, policy.group)]
        while uses and uses[0].at <= at - DAY:
            uses.popleft()
        return [u for u in uses if u.at <= at]


def _fmt(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds % 3600 == 0:
        return f"{seconds // 3600} h"
    if seconds % 60 == 0:
        return f"{seconds // 60} min"
    return f"{seconds} s"


def adult_birth_date_policy(
    exempt_requestors: frozenset[str] = frozenset(),
) -> DatumPolicy:
    """The worked example from the Technical Architecture Paper.

    An adult's birth date under a prior of roughly 70 years (about 25,600
    days), never to be resolved more finely than a year: ``k = 7``, so at
    most 6 queries in any 5-minute window. The daily quota of 5 is stricter
    than that, and each requestor gets at most 3 of the 5.
    """
    return DatumPolicy(
        group="birth_date",
        attributes=frozenset({"date_of_birth", "age", "school_year"}),
        tau=timedelta(minutes=5),
        daily_quota=5,
        requestor_share=3,
        prior_range=70 * 365.25,
        resolution=365.25,
        exempt_requestors=exempt_requestors,
    )
