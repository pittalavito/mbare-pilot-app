"""Request/response models of a project's Atlassian settings. The API token
goes in only: responses say whether one is saved, never its value."""
from pydantic import BaseModel

from models.domain.atlassian import AtlassianSettings, AtlassianUser


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
