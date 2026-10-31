"""Masking: the pure Masker, the per-project map on (fake) Redis, and a whole
agent run where the LLM only sees aliases while tools and user see real values."""
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from core.error import NotFoundError, ValidationError
from domain.masking.masker import Masker
from domain.project.folder_browser import FolderBrowser
from fakes import FakeAgent
from models.domain.agent import AgentConfig
from models.domain.chatbot import ChatMessage, MessageRole
from models.domain.masking import MaskCategory, MaskEntry
from models.domain.project import Project, ProjectSource
from service import agent_service as agent_service_module
from service.chat_service import ChatService
from service.project_service import ProjectService

# ------------------------------------------------------------------ Masker

def _masker(*pairs) -> Masker:
    return Masker([MaskEntry(category=MaskCategory.TERM, value=value, alias=alias) for value, alias in pairs])


def test_mask_is_case_insensitive_whole_word_and_longest_first():
    masker = _masker(("api", "REPO_1"), ("api-gateway", "REPO_2"), ("Mario Rossi", "PERSONA_1"))

    text = "mario rossi ha toccato API e api-gateway, non rapid né apis"

    assert masker.mask(text) == "PERSONA_1 ha toccato REPO_1 e REPO_2, non rapid né apis"


def test_unmask_puts_back_the_first_seen_value_and_leaves_unknown_aliases():
    masker = _masker(("Mario Rossi", "PERSONA_1"))

    assert masker.unmask("PERSONA_1 e PERSONA_9 (REPO_10)") == "Mario Rossi e PERSONA_9 (REPO_10)"


def test_values_with_symbols_are_masked():
    masker = _masker(("mario@gnv.it", "EMAIL_1"), ("C++", "TERMINE_1"))

    assert masker.mask("scrivi a mario@gnv.it, usa C++.") == "scrivi a EMAIL_1, usa TERMINE_1."


def test_empty_map_changes_nothing():
    assert Masker([]).mask("tutto in chiaro") == "tutto in chiaro"


# ------------------------------------------------------------ map on Redis

@pytest.fixture
def masking(masking_service, project_store):
    for name in ("acme", "other"):
        project_store.save(Project(name=name, source=ProjectSource.FOLDER, root_path=f"/code/{name}"))
    return masking_service


def test_aliases_per_category_per_project_never_reused(masking):
    first = masking.register("acme", MaskCategory.REPOSITORY, "project-be")
    again = masking.register("acme", MaskCategory.REPOSITORY, "PROJECT-BE")
    second = masking.register("acme", MaskCategory.REPOSITORY, "project-fe")
    person = masking.add_term("acme", MaskCategory.PERSON, "Mario Rossi")

    assert (first.alias, again.alias, second.alias, person.alias) == ("REPO_1", "REPO_1", "REPO_2", "PERSONA_1")
    assert masking.entries("other") == []
    masking.remove("acme", "REPO_2")
    assert masking.register("acme", MaskCategory.REPOSITORY, "project-fe").alias == "REPO_3"
    assert [(e.alias, e.manual) for e in masking.entries("acme")] == [
        ("PERSONA_1", True), ("REPO_1", False), ("REPO_3", False),
    ]


def test_short_values_and_unknown_aliases(masking):
    assert masking.register("acme", MaskCategory.TERM, "ab") is None
    with pytest.raises(ValidationError):
        masking.add_term("acme", MaskCategory.TERM, " ab ")
    with pytest.raises(NotFoundError):
        masking.remove("acme", "TERMINE_9")
    with pytest.raises(NotFoundError):
        masking.add_term("missing", MaskCategory.TERM, "abc")


def test_removing_the_project_removes_its_map(masking, tmp_path, mask_store, project_store):
    masking.add_term("acme", MaskCategory.TERM, "Grandi Navi")
    masking.add_term("other", MaskCategory.TERM, "Grandi Navi")

    ProjectService(project_store, mask_store, FolderBrowser([tmp_path])).remove("acme")

    assert masking.entries("acme") == [] and len(masking.entries("other")) == 1


# ------------------------------------------------------- whole agent run

class _Recording:
    """An agent that records what the LLM would receive, calls git_status on
    the repository it is told (by alias) and answers with what it saw."""

    def __init__(self, tools, seen):
        self._git_status = next(tool for tool in tools if tool.name == "git_status")
        self._seen = seen

    def run(self, task_input, memory=None):
        self._seen["input"] = task_input
        self._seen["memory"] = [block.content for turn in memory for block in turn.blocks] if memory else []
        self._seen["tool"] = self._git_status(repository=self._seen.get("ask_repo", "REPO_1"))
        return SimpleNamespace(text="Ho controllato REPO_1 per PERSONA_1.")


@pytest.fixture
def agent_service(agent_config_service, masking, tmp_path, monkeypatch, make_agent_service, project_store):
    repo = tmp_path / "acme" / "project-be"
    repo.mkdir(parents=True)
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path / "acme")))
    agent_config_service.save_config(AgentConfig(
        name="bot", project_name="acme", role_name="hello", prompt_id=agent_config_service.latest_prompt("hello").id,
        model="openai/gpt-4o", tool_names=["git_status"],
    ), create=True)
    chat = ChatService()
    monkeypatch.setattr(chat, "get_client", lambda model: object())
    return make_agent_service(chat, masking_service=masking)


def test_the_llm_sees_aliases_the_tools_and_the_user_real_values(agent_service, masking, monkeypatch):
    masking.add_term("acme", MaskCategory.PERSON, "Mario Rossi")
    masking.register("acme", MaskCategory.REPOSITORY, "project-be")
    seen = {}
    monkeypatch.setattr(agent_service_module.AgentFactory, "create_agent",
                        staticmethod(lambda definition, client, tools: _Recording(tools, seen)))
    history = [ChatMessage(conversation_id=1, role=MessageRole.USER, content="ciao, sono Mario Rossi")]

    record = agent_service.run_definition(
        _definition(agent_service), "Mario Rossi chiede: project-be ha modifiche?", project_name="acme", history=history,
    )

    assert seen["input"] == "PERSONA_1 chiede: REPO_1 ha modifiche?"
    assert seen["memory"] == ["ciao, sono PERSONA_1"]
    # the tool got the real repository (else: an error), its output is masked
    assert '"repository":"REPO_1"' in seen["tool"] and "project-be" not in seen["tool"] and "error" not in seen["tool"]
    assert record.output == "Ho controllato project-be per Mario Rossi."
    assert record.input == "Mario Rossi chiede: project-be ha modifiche?"


def test_tools_register_what_they_read(agent_service, masking, monkeypatch, tmp_path):
    """git_status on a repository not in the map yet: registered, and masked in the same output."""
    seen = {"ask_repo": "project-be"}
    monkeypatch.setattr(agent_service_module.AgentFactory, "create_agent",
                        staticmethod(lambda definition, client, tools: _Recording(tools, seen)))

    agent_service.run_definition(_definition(agent_service), "stato?", project_name="acme")

    assert [(e.value, e.alias, e.manual) for e in masking.entries("acme")] == [("project-be", "REPO_1", False)]
    assert '"repository":"REPO_1"' in seen["tool"] and "project-be" not in seen["tool"]


def test_the_projects_repositories_are_masked_from_the_first_message(agent_service, masking, monkeypatch):
    seen = {}

    def create_agent(definition, client, tools):
        agent = FakeAgent()
        original = agent.run

        def run(task_input, memory=None):
            seen["input"] = task_input
            return original(task_input, memory)

        agent.run = run
        return agent

    monkeypatch.setattr(agent_service_module.AgentFactory, "create_agent", staticmethod(create_agent))

    record = agent_service.run_definition(_definition(agent_service), "com'è messo project-be?", project_name="acme")

    assert seen["input"] == "com'è messo REPO_1?"  # no tool called: registered at the start of the run
    assert record.output == "echo: com'è messo project-be?"
    assert [(e.value, e.manual) for e in masking.entries("acme")] == [("project-be", False)]


def test_tool_errors_reach_the_llm_without_paths_nor_real_names(agent_service, monkeypatch, tmp_path):
    seen = {"ask_repo": "nope"}
    monkeypatch.setattr(agent_service_module.AgentFactory, "create_agent",
                        staticmethod(lambda definition, client, tools: _Recording(tools, seen)))

    agent_service.run_definition(_definition(agent_service), "stato di nope?", project_name="acme")

    error = seen["tool"]
    assert "Cartella inesistente" in error and "Repository disponibili: REPO_1" in error
    assert "project-be" not in error and str(tmp_path) not in error and tmp_path.as_posix() not in error


def test_runs_outside_a_project_are_not_masked(agent_service, masking, monkeypatch):
    masking.add_term("acme", MaskCategory.PERSON, "Mario Rossi")
    monkeypatch.setattr(agent_service_module.AgentFactory, "create_agent",
                        staticmethod(lambda definition, client, tools: FakeAgent()))

    record = agent_service.run("hello", "ciao Mario Rossi")

    assert record.output == "echo: ciao Mario Rossi"


def _definition(agent_service):
    from models.domain.agent import AgentDefinition
    return AgentDefinition.from_spec(agent_service._agent_config_service.resolve("bot"))
