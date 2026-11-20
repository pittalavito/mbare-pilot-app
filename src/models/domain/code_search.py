"""A free search in a project's code (plan 23): what to look for, what was found."""
from pydantic import BaseModel, Field


class CodeQuery(BaseModel):
    """What to look for: plain text by default, a regular expression with ``regex``."""
    query: str = Field(min_length=1)
    regex: bool = False
    """``query`` is a regular expression (Python syntax); otherwise plain text, case sensitive."""
    files: str = ""
    """Only the files matching this glob (e.g. ``*.java``, ``src/main/**``); ``""`` = all."""
    repository: str = ""
    """Only this repository (its folder in the project); ``""`` = all of them."""


class CodeMatch(BaseModel):
    path: str
    """Relative to the project folder, ``/`` separators (``<repository>/<file>``)."""
    line: int
    text: str
    """The line, trimmed and cut."""


class CodeSearchResult(BaseModel):
    matches: list[CodeMatch] = []
    """In file order, at most the limit asked."""
    total: int = 0
    """Every match found, also beyond the limit."""
    files: int = 0
    """How many files have at least one match."""
    truncated: bool = False
    """More matches than the ones returned."""


class CodeSearchSaved(BaseModel):
    note: str
    """The code reference written (``code-reference-<title>.md``)."""
    created: bool
    total: int


class SavedSearch(BaseModel):
    """A search with a name (plan 34, «regex parlanti»): defaults in ``code-searches.yml``
    of the definitions, the project's own in its settings (by name, the project's win)."""
    name: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=1)
    regex: bool = True
    files: str = ""
    """Only the files matching this glob; ``""`` = all."""
    description: str = ""
    """What it finds, in words."""


class SavedSearchView(SavedSearch):
    origin: str = "app"
    """``app`` (the definitions), ``progetto`` (written in the project; it may replace a default)."""


class SavedSearchFile(BaseModel):
    """``code-searches.yml`` of the definitions."""
    searches: list[SavedSearch] = []


class RegexAnswer(BaseModel):
    """The structured answer of the agent ``regex`` («✨ Regex»)."""
    regex: str = ""
    """A Python regular expression."""
    explanation: str = ""
    """What it matches, in one or two sentences."""
    example: str = ""
    """A line of code it matches."""


class RegexProposal(RegexAnswer):
    valid: bool = True
    """The regex compiles."""
    example_matches: bool = False
    """The regex finds something in its example."""
    run_id: str
    cost_eur: float = 0.0
