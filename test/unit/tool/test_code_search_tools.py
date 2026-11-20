"""Search_code (Refiner, Dev) gives a few short masked lines;
save_code_search (only Dev) writes the reference linked to the task."""
import json
import shutil
import subprocess

import pytest

from domain.agent.masking import AgentMask
from fakes import as_dict
from models.domain.agent import RunOrigin
from models.domain.chatbot import KIND_TOOLS, ChatbotKind
from models.domain.note import AgentTask
from models.domain.project import Project, ProjectSource
from service.code_search_service import CodeSearchService
from tool.context import ToolContext
from tool.list.code.search import LINE_CHARS, MAX_LINES, SAVE_CODE_SEARCH, SEARCH_CODE
from tool.registry import TOOL_REGISTRY

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


@pytest.fixture
def context(tmp_path, project_store, git_service, project_data_service) -> ToolContext:
    repo = tmp_path / "acme" / "api"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    (repo / "Order.java").write_text("".join(f"// Mario Rossi {i} " + "x" * 300 + "\n" for i in range(40)), encoding="utf-8")
    project_store.save(Project(name="Acme Srl", source=ProjectSource.FOLDER, root_path=str(tmp_path / "acme")))
    return ToolContext(project_name="Acme Srl", git=git_service, origin=RunOrigin.CHAT, project_data=project_data_service,
                       code_search=CodeSearchService(git_service, project_data_service))


def test_search_gives_few_short_lines(context):
    result = as_dict(SEARCH_CODE.build(context).func(query="Mario"))

    assert len(result["matches"]) == MAX_LINES and result["total"] == 40 and result["truncated"]
    assert all(len(line["text"]) <= LINE_CHARS for line in result["matches"]) and result["matches"][0]["path"] == "api/Order.java"


class _Session:
    def mask(self, text):
        return text.replace("Mario Rossi", "PERSONA_1")

    def unmask(self, text):
        return text

    def unmask_value(self, value):
        return value

    def register_all(self, category, values):
        pass


def test_the_agent_sees_the_lines_masked(context):
    [tool] = AgentMask(_Session()).wrap([SEARCH_CODE.build(context)])
    text = tool.func(query="Mario")
    assert "PERSONA_1" in text and "Mario Rossi" not in text


def test_dev_saves_the_search_linked_to_the_task(context):
    task = context.project_data.create_agent_task("Acme Srl", AgentTask(title="Login"))
    result = as_dict(SAVE_CODE_SEARCH.build(context).func(query="Mario", title="Mario", task=task))

    assert result == {"note": "code-reference-mario.md", "created": True, "total": 40,
                      "link": "/projects/Acme%20Srl/project?note=code-reference-mario.md"}
    assert task in context.project_data.linked_from("Acme Srl")["code-reference-mario.md"]
    assert "indica il task" in json.dumps(as_dict(SAVE_CODE_SEARCH.build(context).func(query="Mario"))).lower()
    assert "query" in as_dict(SEARCH_CODE.build(context).func(query="  "))["error"]


def test_only_in_a_chatbot_and_only_dev_saves(context):
    for other in (
        ToolContext(project_name="Acme Srl", git=context.git, origin=RunOrigin.MANUAL, code_search=context.code_search),
        ToolContext(project_name=None, git=context.git, origin=RunOrigin.CHAT, code_search=context.code_search),
        ToolContext(project_name="Acme Srl", git=context.git, origin=RunOrigin.CHAT),
    ):
        assert "solo nel chatbot di un progetto" in as_dict(SEARCH_CODE.build(other).func(query="x"))["error"]
    assert "search_code" in KIND_TOOLS[ChatbotKind.REFINER] and "save_code_search" not in KIND_TOOLS[ChatbotKind.REFINER]
    assert {"search_code", "save_code_search"} <= set(KIND_TOOLS[ChatbotKind.OPERATOR])
    assert SAVE_CODE_SEARCH.writes and SEARCH_CODE.chatbot_only
    assert not {"create_code_reference", "clean_mbare_pilot"} & set(TOOL_REGISTRY)
