"""Projects: open an existing code folder or create a new one from scratch,
list, update and remove them. Every path goes through FolderBrowser, so it
stays inside the configured roots."""
import os
from pathlib import Path

from core.error import ConflictError, NotFoundError, ValidationError
from core.observability import LogPrefix, observed
from domain.project.data_paths import project_slug
from domain.project.folder_browser import FolderBrowser
from models.domain.chat import EmbeddingModelName
from models.domain.project import Project, ProjectSource
from service.store_service import StoreService


class ProjectService:

    def __init__(self, store_service: StoreService, folder_browser: FolderBrowser):
        self._store = store_service
        self._folders = folder_browser

    @property
    def folders(self) -> FolderBrowser:
        """The folder browser, for the picker UI."""
        return self._folders

    def list_projects(self, source: ProjectSource | None = None) -> list[Project]:
        return self._store.list_projects(source)

    def get_project(self, name: str) -> Project:
        project = self._store.get_project(name)
        if project is None:
            raise NotFoundError(f"Progetto non trovato: {name}")
        return project

    @observed(LogPrefix.PROJECT_SERVICE)
    def open_folder(self, name: str, description: str, folder: str | Path) -> Project:
        """Register an existing folder as a project."""
        project = Project(name=name, description=description, source=ProjectSource.FOLDER,
                          root_path=str(self._folders.resolve(folder)))
        self._require_unique(project)
        return self._store.save_project(project)

    @observed(LogPrefix.PROJECT_SERVICE)
    def create_from_scratch(self, name: str, description: str, parent: str | Path, folder_name: str) -> Project:
        """Create ``parent/folder_name`` and register it as a project. The
        folder is removed again if the project cannot be saved."""
        draft = Project(name=name, description=description, source=ProjectSource.SCRATCH,
                        root_path=str(self._folders.resolve(parent) / folder_name.strip()))
        self._require_unique(draft)
        folder = self._folders.create_folder(parent, folder_name)
        try:
            return self._store.save_project(draft.model_copy(update={"root_path": str(folder)}))
        except Exception:
            folder.rmdir()
            raise

    def update(self, name: str, *, description: str, embedding_model: EmbeddingModelName) -> Project:
        """Editable settings; name, source and folder are fixed."""
        project = self.get_project(name)
        return self._store.save_project(
            project.model_copy(update={"description": description.strip(), "embedding_model": embedding_model}),
        )

    def remove(self, name: str) -> bool:
        """Remove the project and everything it owns in the DB (its agents,
        chatbots, pipelines, RAG index). Its code folder and its data folder
        on disk are untouched. Its masking map goes too."""
        removed = self._store.delete_project(name)
        if removed:
            self._store.delete_masks(name)
        return removed

    def folder_exists(self, project: Project) -> bool:
        return Path(project.root_path).is_dir()

    def _require_unique(self, project: Project) -> None:
        if "/" in project.name or "\\" in project.name:
            # names travel in API paths (/projects/{name}) and become folder slugs
            raise ValidationError("Il nome del progetto non può contenere / o \\.")
        if self._store.get_project(project.name) is not None:
            raise ConflictError(f"Esiste già un progetto chiamato {project.name}.")
        wanted = os.path.normcase(project.root_path)
        slug = project_slug(project.name)
        for existing in self._store.list_projects():
            if project_slug(existing.name) == slug:
                raise ConflictError(f"Il nome è troppo simile a quello del progetto {existing.name}.")
            if os.path.normcase(existing.root_path) == wanted:
                raise ConflictError(f"Questa cartella è già il progetto {existing.name}.")
