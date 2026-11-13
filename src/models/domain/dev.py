"""The checks around a development task delegated to Copilot (blocco 09):
«Prepara sviluppo» before Copilot, «Verifica sviluppo» after it."""
from enum import StrEnum

from pydantic import BaseModel, Field


class TestKind(StrEnum):
    __test__ = False  # not a pytest class
    MAVEN = "maven"
    PYTHON = "python"
    NODE = "node"
    UNKNOWN = "unknown"


class TestScope(StrEnum):
    """Which tests the «Verifica sviluppo» runs."""
    __test__ = False
    ALL = "all"
    TOUCHED = "touched"


PREPARE_AUTOMATION = "Prepara sviluppo"
"""The project's automation run at the delegation, before Copilot (none = no preparation)."""
VERIFY_AUTOMATION = "Verifica sviluppo"
"""The project's automation run when a development goes «to verify» (none = no verification)."""


VERIFY_OK = "🔍 Verifica ok."
VERIFY_FAILED = "🔍 Verifica fallita."
"""How the chat event of a failed verification starts: the UI offers it as the message to send back to Copilot."""


class PrepareTarget(BaseModel):
    """A repository to get ready, on ``branch``: an existing one, or a new one from ``base``."""
    repository: str = ""
    """The repository's folder in the project; ``""`` = the project folder itself."""
    branch: str = Field(min_length=1)
    base: str = ""
    """Where a new branch starts from (a branch); ``""`` = the branch must exist."""


class LearnedPreparation(BaseModel):
    """An automation learned from the Operator, run at the delegation instead of «Prepara sviluppo» (plan 11)."""
    automation_id: int
    fields: dict[str, str] = {}
    """Its fields' values (the delegation fills them from the task; the user corrects them)."""


class DevCheck(BaseModel):
    """How a preparation or a verification went."""
    ok: bool
    skipped: bool = False
    """The project has no such automation: nothing was run."""
    text: str
    """What to show: each step's output, or the error."""
    run_id: int | None = None
    """The automation's run (Admin → Observability)."""


class RepositoryTests(BaseModel):
    """The tests of one repository of the project, for the settings."""
    repository: str
    kind: TestKind
    detected_command: str
    """From the files at its root; ``""`` = unknown tool."""
    command: str
    """The one written in the settings; ``""`` = the detected one."""


class DevSettings(BaseModel):
    test_scope: TestScope = TestScope.ALL
    """The default: every test, or only the touched ones (a task can change it)."""
    repositories: list[RepositoryTests] = []
