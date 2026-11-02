"""The refiner's tool: it writes the todoMbarePilot comments into a code
reference and hands the agent only counts and the note's link."""
import json
import shutil
import subprocess

import pytest

from fakes import as_dict
from models.domain.agent import RunOrigin
from models.domain.note import NoteType, Reference
from models.domain.project import Project, ProjectSource
from service.code_todo_service import CodeTodoService
from tool.context import ToolContext
from tool.list.refiner.create_code_reference import CREATE_CODE_REFERENCE

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

SECRET = "Password admin in chiaro"


@pytest.fixture
def context(tmp_path, project_store, git_service, project_data_service) -> ToolContext:
    """Chatbot run of project «Acme Srl» (repository ``api`` with one comment)."""
    repo = tmp_path / "acme" / "api"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    (repo / "login.py").write_text(f"# todoMbarePilot{{{SECRET}}}\n", encoding="utf-8")
    project_store.save(Project(name="Acme Srl", source=ProjectSource.FOLDER, root_path=str(tmp_path / "acme")))
    return ToolContext(project_name="Acme Srl", git=git_service, origin=RunOrigin.CHAT, project_data=project_data_service,
                       code_todos=CodeTodoService(git_service, project_data_service))


def _call(context: ToolContext) -> dict:
    return as_dict(CREATE_CODE_REFERENCE.build(context).func())


def test_the_agent_gets_counts_and_the_link_never_the_comments(context):
    result = _call(context)

    assert result == {
        "note": "code-reference-todo-mbare-pilot.md", "created": True, "files": 1, "comments": 1,
        "link": "/projects/Acme%20Srl/data?note=code-reference-todo-mbare-pilot.md",
    }
    assert SECRET not in json.dumps(result) and "login.py" not in json.dumps(result)
    assert SECRET in context.project_data.reference("Acme Srl", result["note"])[1].content  # the user reads them in the note
    assert _call(context)["created"] is False  # the same note, rewritten


def test_nothing_found_means_no_note_and_no_link(context, tmp_path):
    (tmp_path / "acme" / "api" / "login.py").write_text("x = 1\n", encoding="utf-8")

    assert _call(context) == {"note": None, "created": False, "files": 0, "comments": 0, "link": None}


def test_errors_and_runs_outside_a_chatbot(context):
    context.project_data.create_reference("Acme Srl", NoteType.CODE_REFERENCE, Reference(title="TODO Mbare Pilot", content="mio"))
    assert "scritto a mano" in _call(context)["error"]

    for other in (
        ToolContext(project_name="Acme Srl", git=context.git, origin=RunOrigin.MANUAL, code_todos=context.code_todos),
        ToolContext(project_name=None, git=context.git, origin=RunOrigin.CHAT, code_todos=context.code_todos),
        ToolContext(project_name="Acme Srl", git=context.git, origin=RunOrigin.CHAT),
    ):
        assert "solo nel chatbot di un progetto" in _call(other)["error"]
