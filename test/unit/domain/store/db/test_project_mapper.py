"""Projects from DB rows: the note types saved before a rename still read."""
from datetime import datetime, timezone

from domain.store.db.project_mapper import Adapter, Factory
from models.domain.note import NoteType
from models.domain.project import Project, ProjectSource
from models.store.db import ProjectTable


def _row(**fields) -> ProjectTable:
    return ProjectTable(name="p", source="folder", root_path="/p", embedding_model=Project.model_fields["embedding_model"].default.value,
                        created_at=datetime(2026, 11, 3, tzinfo=timezone.utc), **fields)


def test_a_saved_todo_list_reads_as_activity_and_unknown_types_are_dropped():
    project = Adapter.to_project(_row(visible_note_types=["generic", "todo_list", "boh", "activity"]))

    assert project.visible_note_types == [NoteType.GENERIC, NoteType.ACTIVITY]  # once, in the saved order


def test_files_visible_and_no_choice_round_trip():
    project = Project(name="p", source=ProjectSource.FOLDER, root_path="/p", files_visible=False)

    back = Adapter.to_project(Factory.to_project_row(project))

    assert (back.files_visible, back.visible_note_types) == (False, None)
