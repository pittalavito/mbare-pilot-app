"""Development around Copilot (blocco 09, plan 22): the tests' settings and
the repositories to get ready (the dev tools' inputs)."""
from enum import StrEnum

from pydantic import BaseModel, Field


class TestKind(StrEnum):
    __test__ = False  # not a pytest class
    MAVEN = "maven"
    PYTHON = "python"
    NODE = "node"
    UNKNOWN = "unknown"


class TestScope(StrEnum):
    """Which tests ``run_tests`` runs."""
    __test__ = False
    ALL = "all"
    TOUCHED = "touched"


class PrepareTarget(BaseModel):
    """A repository to get ready, on ``branch``: an existing one, or a new one from ``base``."""
    repository: str = ""
    """The repository's folder in the project; ``""`` = the project folder itself."""
    branch: str = Field(min_length=1)
    base: str = ""
    """Where a new branch starts from (a branch); ``""`` = the branch must exist."""


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
