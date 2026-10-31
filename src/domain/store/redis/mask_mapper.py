"""Masking maps: Redis ``MaskRecord`` -> domain ``MaskEntry`` (the records are
written by the repository itself, which assigns the alias)."""
from models.domain.masking import MaskCategory, MaskEntry
from models.store.redis import MaskRecord


class Adapter:
    """Read seam: Redis records -> domain models."""

    @staticmethod
    def to_mask_entry(record: MaskRecord) -> MaskEntry:
        return MaskEntry(category=MaskCategory(record.category), value=record.value, alias=record.alias,
                         manual=record.manual)
