"""Output contracts of the tools, one model per tool."""
from pydantic import BaseModel, Field

from models.domain.git import GitStatus


class ToolErrorResponse(BaseModel):
    """Returned instead of raising, so the agent can read the problem and retry."""
    error: str = Field(..., description="What went wrong and how to fix the call.")


class HelloWorldResponse(BaseModel):
    response: str = Field(..., description="The greeting message.")


class GitStatusResponse(BaseModel):
    repository: str = Field(..., description="Repository folder inside the project ('' = the project folder).")
    clean: bool = Field(..., description="True when no file is changed.")
    status: GitStatus

