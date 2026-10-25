"""AgentMask, the one place where an agent run masks: what the LLM receives is
masked, what comes back is unmasked, the tools' output is serialized, its
sensitive fields registered and masked. Pure: a fake session stands in for the
project's map (the real one is covered in test/unit/service/test_masking.py)."""
import datetime
from pathlib import Path

from datapizza.tools import tool
from pydantic import BaseModel

from domain.agent.masking import AgentMask
from models.domain.chatbot import ChatMessage, MessageRole
from models.domain.git import GitCommit, GitStatus
from models.domain.masking import MaskCategory, MaskRepositoryName, MaskRepositoryNames, sensitive_values
from models.domain.tool import GitPullResponse, GitStatusResponse, ToolErrorResponse
from tool.context import ToolContext


class _Session:
    """Masks by plain replacement: value → ``ALIAS_n``, in the order registered."""

    def __init__(self):
        self.aliases: dict[str, str] = {}
        self.registered: list[tuple[MaskCategory, str]] = []

    def register_all(self, category, values):
        for value in values:
            self.registered.append((category, value))
            self.aliases.setdefault(value, f"ALIAS_{len(self.aliases) + 1}")

    def mask(self, text):
        for value, alias in self.aliases.items():
            text = text.replace(value, alias)
        return text

    def unmask(self, text):
        for value, alias in self.aliases.items():
            text = text.replace(alias, value)
        return text

    def unmask_value(self, value):
        if isinstance(value, str):
            return self.unmask(value)
        if isinstance(value, dict):
            return {key: self.unmask_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return type(value)(self.unmask_value(item) for item in value)
        return value


class _Output(BaseModel):
    repository: MaskRepositoryName
    note: str = ""
    repositories: MaskRepositoryNames = []


@tool
def describe(repository: str) -> BaseModel:
    """Describes a repository."""
    return _Output(repository=repository, note=f"fatto su {repository}")


@tool
def failing(repository: str) -> BaseModel:
    """Fails naming the repositories it can use."""
    return ToolErrorResponse(error=f"{repository} non valido.", repositories=["project-fe", "project-be"])


def _wrapped(session, *tools):
    return AgentMask(session).wrap(list(tools))


def test_output_is_serialized_its_sensitive_fields_registered_and_masked():
    session = _Session()
    [tool] = _wrapped(session, describe)

    text = tool.func(repository="project-be")

    assert text.startswith("{") and '"repository":"ALIAS_1"' in text and "project-be" not in text
    assert session.registered == [(MaskCategory.REPOSITORY, "project-be")]


def test_arguments_come_in_unmasked_so_the_tool_works_on_real_values():
    session = _Session()
    session.register_all(MaskCategory.REPOSITORY, ["project-be"])
    [tool] = _wrapped(session, describe)

    assert '"repository":"ALIAS_1"' in tool.func(repository="ALIAS_1")  # the tool saw project-be, the output is masked


def test_error_responses_register_the_repositories_they_name():
    session = _Session()
    [tool] = _wrapped(session, failing)

    text = tool.func(repository="x")

    assert {value for _, value in session.registered} == {"project-fe", "project-be"}
    assert "project-fe" not in text and "project-be" not in text


def test_the_project_repositories_are_masked_before_any_tool_runs():
    session = _Session()

    AgentMask(session, ["project-be", "project-fe"])

    assert session.registered == [(MaskCategory.REPOSITORY, "project-be"), (MaskCategory.REPOSITORY, "project-fe")]


def test_input_and_history_go_to_the_llm_masked_and_answers_come_back_unmasked():
    session = _Session()
    session.register_all(MaskCategory.REPOSITORY, ["project-be"])
    mask = AgentMask(session)
    history = [ChatMessage(conversation_id=1, role=MessageRole.USER, content="project-be ok?")]

    assert mask.input("controlla project-be") == "controlla ALIAS_1"
    assert [message.content for message in mask.history(history)] == ["ALIAS_1 ok?"]
    assert history[0].content == "project-be ok?"  # the conversation itself is not touched
    assert mask.answer("ALIAS_1 è pronto") == "project-be è pronto"


def test_without_a_session_nothing_is_masked_or_registered_but_outputs_are_still_serialized():
    mask = AgentMask(None, ["project-be"])
    [tool] = mask.wrap([describe])

    assert mask.input("project-be") == "project-be" and mask.answer("ALIAS_1") == "ALIAS_1"
    assert '"repository":"project-be"' in tool.func(repository="project-be")


def test_static_tools_returning_text_pass_through_masked():
    session = _Session()
    session.register_all(MaskCategory.REPOSITORY, ["project-be"])

    @tool
    def plain() -> str:
        """Plain text."""
        return "project-be ok"

    [masked] = _wrapped(session, plain)

    assert masked.func() == "ALIAS_1 ok"


# ------------------------------------------------------------ sensitive_values

def test_only_the_marked_fields_are_sensitive_nested_models_included():
    commit = GitCommit(hash="1", short_hash="1", author="Bob", email="bob@example.com",
                       date=datetime.datetime(2026, 10, 25), subject="second")
    response = GitPullResponse(repository="api", branch="main", upstream="origin/main", updated=True, commits=[commit])

    assert set(sensitive_values(response)) == {
        (MaskCategory.REPOSITORY, "api"), (MaskCategory.PERSON, "Bob"), (MaskCategory.EMAIL, "bob@example.com"),
    }


def test_unmarked_text_is_never_sensitive():
    response = GitStatusResponse(repository="api", clean=True, status=GitStatus(branch="main", changes=[]))

    assert list(sensitive_values(response)) == [(MaskCategory.REPOSITORY, "api")]


def test_empty_values_are_not_registered():
    assert list(sensitive_values(_Output(repository="", repositories=["", "x"]))) == [(MaskCategory.REPOSITORY, "x")]


# -------------------------------------------------------------- the boundary

def test_tools_neither_see_the_session_nor_mask_anything():
    """Masking lives in the agent layer: ToolContext has no session, and no tool
    module imports the masking services or registers values."""
    assert "mask" not in ToolContext.__dataclass_fields__
    tools_dir = Path(__file__).resolve().parents[4] / "src" / "tool"
    for path in tools_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("MaskSession", "masking_service", "MaskCategory", "register_sensitive"):
            assert forbidden not in text, f"{path.name} mentions {forbidden}"
