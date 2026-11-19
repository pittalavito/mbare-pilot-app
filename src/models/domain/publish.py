"""Publishing a draft (``bozza-confluence-<task>.md``, ``bozza-jira-<task>.md``) of a Confluence or Jira task (blocco 10)."""
from enum import StrEnum

from pydantic import BaseModel


class PublishKind(StrEnum):
    CONFLUENCE = "confluence"
    JIRA = "jira"


class PublishMode(StrEnum):
    CREATE = "create"
    """A new page / issue."""
    UPDATE = "update"
    """The page / issue the task links as a reference."""


class PublishPreview(BaseModel):
    """What «Pubblica» would do, shown before the user confirms."""
    kind: PublishKind
    mode: PublishMode
    draft: str
    """The draft note's name."""
    title: str
    """The page's title, or the new issue's summary (an updated issue keeps its own)."""
    body: str
    """The draft's body as it will be published (Markdown, aliases replaced by the real values)."""
    unmasked: list[str] = []
    """The aliases replaced: ``REPO_1 → api``."""
    reference: str | None = None
    """UPDATE: the linked reference the target comes from."""
    target_title: str = ""
    target_body: str = ""
    """UPDATE: the page's or issue's current text (Markdown), for the comparison."""
    target_url: str = ""
    space_key: str = ""
    project_key: str = ""
    """CREATE: the project's default Confluence space / Jira project (the task's space, when it has one)."""
    parent_id: str = ""
    parent_title: str = ""
    parent_kind: str = ""
    """CREATE: the parent page or folder the task says (plan 32); ``""`` = none (the UI offers the last place used)."""
    parent_error: str = ""
    """Why the task's parent could not be read (wrong link, no access)."""


class PublishResult(BaseModel):
    kind: PublishKind
    mode: PublishMode
    url: str
    reference: str
    """The context reference linked to the task (created or refreshed)."""
    draft: str = ""
    """The draft published, deleted after (plan 33)."""
