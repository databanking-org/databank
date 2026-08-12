"""Record storage.

In-memory only. Persistence is a stub because the interesting questions are
not which database to use but where records may physically reside, how long
they are retained, and what happens on the owner's death or a Databank's
insolvency -- see the case studies at https://databanking.org.
"""

from __future__ import annotations

from databank.models import Record


class RecordStore:
    """Keyed by ``(owner_id, attribute)``; one value per attribute."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], Record] = {}

    def put(self, record: Record) -> None:
        self._records[(record.owner_id, record.attribute)] = record

    def get(self, owner_id: str, attribute: str) -> Record | None:
        return self._records.get((owner_id, attribute))

    def erase(self, owner_id: str, attribute: str) -> bool:
        """Erase one attribute. Returns whether anything was removed."""
        return self._records.pop((owner_id, attribute), None) is not None

    def attributes(self, owner_id: str) -> list[str]:
        return sorted(a for (o, a) in self._records if o == owner_id)


def persist(store: RecordStore, destination: str) -> None:
    """Write a store to durable storage.

    STUB. Deliberately unimplemented: a durable store raises residency,
    retention, and succession questions that the reference implementation
    should not answer by accident.
    """
    raise NotImplementedError("durable persistence is not implemented")
