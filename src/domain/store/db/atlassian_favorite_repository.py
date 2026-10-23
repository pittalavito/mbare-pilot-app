"""Favorite Jira issues and Confluence pages of each project (table atlassian_favorite)."""
from sqlalchemy.engine import Engine
from sqlmodel import select

from domain.store.db.repository import SqlRepository
from models.store.db import AtlassianFavoriteTable


class DbAtlassianFavoriteRepository(SqlRepository[AtlassianFavoriteTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, AtlassianFavoriteTable)

    def list_for_project(self, project_name: str) -> list[AtlassianFavoriteTable]:
        """Oldest first, so the list does not reorder as favorites are added."""
        statement = (
            select(AtlassianFavoriteTable).where(AtlassianFavoriteTable.project_name == project_name)
            .order_by(AtlassianFavoriteTable.id)
        )
        with self._session() as session:
            return list(session.exec(statement).all())

    def find(self, project_name: str, kind: str, ref: str) -> AtlassianFavoriteTable | None:
        statement = select(AtlassianFavoriteTable).where(
            AtlassianFavoriteTable.project_name == project_name,
            AtlassianFavoriteTable.kind == kind,
            AtlassianFavoriteTable.ref == ref,
        )
        with self._session() as session:
            return session.exec(statement).first()
