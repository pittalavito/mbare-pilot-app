"""Atlassian Cloud domain models (Jira projects/issues, Confluence spaces/pages),
already flattened from the REST payloads: rich text comes as plain text."""
from datetime import datetime

from pydantic import BaseModel, SecretStr


class AtlassianSettings(BaseModel):
    """A project's Atlassian Cloud site: credentials plus its default Jira
    project and Confluence space (both optional)."""
    project_name: str
    base_url: str = ""
    """Site URL, e.g. ``https://acme.atlassian.net``."""
    email: str = ""
    api_token: SecretStr = SecretStr("")
    """Personal API token: https://id.atlassian.com/manage-profile/security/api-tokens"""
    jira_project_key: str = ""
    confluence_space_key: str = ""

    @property
    def is_complete(self) -> bool:
        return bool(self.base_url and self.email and self.api_token.get_secret_value())


class AtlassianUser(BaseModel):
    """The account the API token belongs to (connection check)."""
    account_id: str
    display_name: str
    email: str | None = None


# ---------------------------------------------------------------------- Jira

class JiraProject(BaseModel):
    id: str
    key: str
    name: str
    project_type: str | None = None
    url: str


class JiraIssue(BaseModel):
    key: str
    summary: str
    status: str | None = None
    issue_type: str | None = None
    priority: str | None = None
    assignee: str | None = None
    updated: datetime | None = None
    description: str = ""
    """Plain text extracted from the Atlassian Document Format body."""
    url: str


# ---------------------------------------------------------------- Confluence

class ConfluenceSpace(BaseModel):
    id: str
    key: str
    name: str
    space_type: str | None = None
    url: str


class ConfluencePage(BaseModel):
    id: str
    title: str
    space_id: str | None = None
    url: str
    body: str = ""
    """Plain text extracted from the storage (XHTML) body; empty in listings."""


class ConfluenceSearchHit(BaseModel):
    id: str
    title: str
    excerpt: str = ""
    url: str
