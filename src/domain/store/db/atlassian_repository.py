"""Atlassian site of each project (table project_atlassian)."""
from sqlalchemy.engine import Engine

from domain.store.db.repository import SqlRepository
from models.store.db import ProjectAtlassianTable


class DbAtlassianRepository(SqlRepository[ProjectAtlassianTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, ProjectAtlassianTable)
