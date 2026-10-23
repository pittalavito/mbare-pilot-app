"""Request/response models of a project's Atlassian site: its settings (the
API token goes in only: responses say whether one is saved, never its value)
and what is read from Jira and Confluence."""
from datetime import datetime

from pydantic import BaseModel

from models.domain.atlassian import (
    AtlassianFavorite, AtlassianSettings, AtlassianUser, ConfluencePage, ConfluenceSearchHit, FavoriteKind, JiraIssue,
)


class AtlassianSettingsResponse(BaseModel):
    base_url: str
    email: str
    has_token: bool
    jira_project_key: str
    confluence_space_key: str

    @classmethod
    def from_settings(cls, settings: AtlassianSettings) -> "AtlassianSettingsResponse":
        return cls(
            base_url=settings.base_url, email=settings.email, has_token=bool(settings.api_token.get_secret_value()),
            jira_project_key=settings.jira_project_key, confluence_space_key=settings.confluence_space_key,
        )


class AtlassianSettingsRequest(BaseModel):
    base_url: str
    email: str
    api_token: str = ""
    """Empty = keep the saved one."""
    jira_project_key: str = ""
    confluence_space_key: str = ""


class AtlassianUserResponse(BaseModel):
    display_name: str
    email: str | None

    @classmethod
    def from_user(cls, user: AtlassianUser) -> "AtlassianUserResponse":
        return cls(display_name=user.display_name, email=user.email)


class JiraIssueResponse(BaseModel):
    key: str
    summary: str
    status: str | None
    issue_type: str | None
    priority: str | None
    assignee: str | None
    updated: datetime | None
    description: str
    """Plain text."""
    url: str

    @classmethod
    def from_issue(cls, issue: JiraIssue) -> "JiraIssueResponse":
        return cls(**issue.model_dump())


class ConfluencePageResponse(BaseModel):
    id: str
    title: str
    url: str
    body: str
    """Plain text; empty in listings."""

    @classmethod
    def from_page(cls, page: ConfluencePage) -> "ConfluencePageResponse":
        return cls(**page.model_dump())


class ConfluenceSearchHitResponse(BaseModel):
    id: str
    title: str
    excerpt: str
    url: str

    @classmethod
    def from_hit(cls, hit: ConfluenceSearchHit) -> "ConfluenceSearchHitResponse":
        return cls(**hit.model_dump())


class FavoriteResponse(BaseModel):
    id: int
    kind: str
    """``jira_issue`` | ``confluence_page``."""
    ref: str
    """Issue key or page id."""
    title: str
    url: str
    created_at: datetime

    @classmethod
    def from_favorite(cls, favorite: AtlassianFavorite) -> "FavoriteResponse":
        return cls(**favorite.model_dump())


class FavoriteRequest(BaseModel):
    kind: FavoriteKind
    ref: str
    title: str
    url: str = ""
