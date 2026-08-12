"""Access fees and the owner's statutory share.

The whitepaper proposes that a requestor pays an access fee and the owner
receives a statutory share of it. That is a policy parameter, not an
engineering one: the split, the floor, and who sets them are matters for
legislation, so this module deliberately declines to invent numbers.
"""

from __future__ import annotations

from typing import Any


def access_fee(query: Any, bits_disclosed: int) -> Any:
    """Price a query.

    STUB. Whether pricing tracks bits disclosed, sensitivity of the
    attribute, or a flat tariff is unresolved, and the choice has
    distributional consequences -- per-bit pricing would make cheap queries
    about sensitive attributes attractive.
    """
    raise NotImplementedError("access fee calculation is not implemented")


def owner_share(fee: Any, jurisdiction: str) -> Any:
    """Split a fee between owner and Databank.

    STUB. Statutory, and jurisdiction-specific by construction.
    """
    raise NotImplementedError("statutory share calculation is not implemented")
