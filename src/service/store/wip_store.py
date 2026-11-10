"""The «Elabora WIP» runs and what the user did with their proposals (Postgres)."""
from sqlalchemy.engine import Engine

from domain.store.db.wip_mapper import Adapter, Factory
from domain.store.db.wip_repository import DbWipRunRepository
from models.domain.wip import WipRun


class WipStore:

    def __init__(self, engine: Engine):
        self._runs = DbWipRunRepository(engine)

    def save_run(self, run: WipRun) -> WipRun:
        """New or updated (by ``id``)."""
        return Adapter.to_wip_run(self._runs.save(Factory.to_wip_run_row(run)))

    def get_run(self, run_id: str) -> WipRun | None:
        row = self._runs.find(run_id)
        return Adapter.to_wip_run(row) if row else None

    def list_runs(self, project_name: str) -> list[WipRun]:
        """Newest first."""
        return [Adapter.to_wip_run(row) for row in self._runs.list_for_project(project_name)]
