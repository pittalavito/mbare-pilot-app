"""Projects: domain ``Project`` <-> ``project`` rows."""
from domain.store.db.mapper import as_utc
from models.domain.chat import EmbeddingModelName
from models.domain.note import NoteType
from models.domain.project import Project, ProjectSource
from models.store.db import ProjectTable


class Adapter:
    """Read seam: DB rows -> domain models."""

    @staticmethod
    def to_project(row: ProjectTable) -> Project:
        return Project(
            name=row.name,
            description=row.description,
            source=ProjectSource(row.source),
            root_path=row.root_path,
            embedding_model=EmbeddingModelName(row.embedding_model),
            visible_note_types=[NoteType(value) for value in row.visible_note_types if value in NoteType.__members__.values()]
            if row.visible_note_types is not None else None,
            created_at=as_utc(row.created_at),
        )


class Factory:
    """Write seam: domain models -> DB rows."""

    @staticmethod
    def to_project_row(project: Project) -> ProjectTable:
        return ProjectTable(
            name=project.name,
            description=project.description,
            source=project.source.value,
            root_path=project.root_path,
            embedding_model=project.embedding_model.value,
            visible_note_types=[kind.value for kind in project.visible_note_types] if project.visible_note_types is not None else None,
            created_at=project.created_at,
        )
