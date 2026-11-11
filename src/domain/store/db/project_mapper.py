"""Projects: domain ``Project`` <-> ``project`` rows."""
from domain.store.db.mapper import as_utc
from models.domain.chat import EmbeddingModelName
from models.domain.dev import TestScope
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
            visible_note_types=_note_types(row.visible_note_types) if row.visible_note_types is not None else None,
            files_visible=row.files_visible,
            due_soon_days=row.due_soon_days,
            test_scope=TestScope(row.test_scope) if row.test_scope in set(TestScope) else TestScope.ALL,
            test_commands=dict(row.test_commands or {}),
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
            files_visible=project.files_visible,
            due_soon_days=project.due_soon_days,
            test_scope=project.test_scope.value,
            test_commands=dict(project.test_commands) or None,
            created_at=project.created_at,
        )


_RENAMED_NOTE_TYPES = {"todo_list": NoteType.ACTIVITY.value}
"""Saved before a type was renamed: read as the new one."""


def _note_types(values: list[str]) -> list[NoteType]:
    """The saved values that are note types (renamed ones as the new name); unknown ones dropped."""
    known = set(NoteType.__members__.values())
    return list(dict.fromkeys(NoteType(_RENAMED_NOTE_TYPES.get(value, value)) for value in values
                              if _RENAMED_NOTE_TYPES.get(value, value) in known))
