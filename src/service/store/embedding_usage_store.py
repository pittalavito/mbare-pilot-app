"""The calls to a remote embedder (plan 31): tokens and cost, for the Metriche page."""
from datetime import datetime, timezone

from sqlalchemy.engine import Engine
from sqlmodel import col, select

from domain.store.db.repository import SqlRepository
from models.domain.metrics import EmbeddingUsage
from models.store.db import EmbeddingUsageTable


class EmbeddingUsageStore(SqlRepository[EmbeddingUsageTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, EmbeddingUsageTable)

    def add(self, project_name: str, model: str, purpose: str, tokens: int, cost_eur: float) -> None:
        self.save(EmbeddingUsageTable(project_name=project_name, model=model, purpose=purpose, tokens=tokens, cost_eur=cost_eur,
                                      created_at=datetime.now(timezone.utc)))

    def usage_since(self, since: datetime | None, project_name: str | None) -> list[EmbeddingUsage]:
        """Calls, tokens and cost by model and purpose."""
        statement = select(EmbeddingUsageTable)
        if since is not None:
            statement = statement.where(col(EmbeddingUsageTable.created_at) >= since)
        if project_name:
            statement = statement.where(EmbeddingUsageTable.project_name == project_name)
        totals: dict[tuple[str, str], EmbeddingUsage] = {}
        with self._session() as session:
            for row in session.exec(statement).all():
                current = totals.setdefault((row.model, row.purpose), EmbeddingUsage(model=row.model, purpose=row.purpose))
                current.calls += 1
                current.tokens += row.tokens
                current.cost_eur = round(current.cost_eur + row.cost_eur, 8)
        return sorted(totals.values(), key=lambda item: (-item.cost_eur, item.model, item.purpose))
