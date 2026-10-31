"""The projects (name, code folder, embedding model, visible note types).
Almost every service checks that a project exists before touching its data,
so most of them receive this store."""
from sqlalchemy.engine import Engine

from domain.store.db.project_mapper import Adapter, Factory
from domain.store.db.project_repository import DbProjectRepository
from models.domain.project import Project, ProjectSource


class ProjectStore:

    def __init__(self, engine: Engine):
        self._projects = DbProjectRepository(engine)

    def list(self, source: ProjectSource | None = None) -> list[Project]:
        """Projects, most recent first."""
        rows = self._projects.list_recent(source.value if source else None)
        return [Adapter.to_project(row) for row in rows]

    def get(self, name: str) -> Project | None:
        row = self._projects.get(name)
        return Adapter.to_project(row) if row else None

    def save(self, project: Project) -> Project:
        return Adapter.to_project(self._projects.save(Factory.to_project_row(project)))

    def delete(self, name: str) -> bool:
        """The rows of its chatbots, automations, ... go with it (DB cascade)."""
        return self._projects.delete(name)
