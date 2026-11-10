"""«Elabora WIP» runs: domain ``WipRun`` <-> ``wip_run`` rows."""
from domain.store.db.mapper import as_utc
from models.domain.wip import WipRun
from models.store.db import WipRunTable


class Adapter:
    """Read seam: DB rows -> domain models."""

    @staticmethod
    def to_wip_run(row: WipRunTable) -> WipRun:
        run = WipRun.model_validate(row.model_dump())
        run.created_at = as_utc(run.created_at)
        run.applied_at = as_utc(run.applied_at) if run.applied_at else None
        return run


class Factory:
    """Write seam: domain models -> DB rows."""

    @staticmethod
    def to_wip_run_row(run: WipRun) -> WipRunTable:
        return WipRunTable(**run.model_dump())
