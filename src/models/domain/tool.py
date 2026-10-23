"""Output contracts of the tools, one model per tool."""
from pydantic import BaseModel, Field

from models.domain.git import GitCommit, GitStatus


class ToolErrorResponse(BaseModel):
    """Returned instead of raising, so the agent can read the problem and retry."""
    error: str = Field(..., description="What went wrong and how to fix the call.")


class HelloWorldResponse(BaseModel):
    response: str = Field(..., description="The greeting message.")


class WordCountResponse(BaseModel):
    words: int = Field(..., description="Number of whitespace-separated words.")
    characters: int = Field(..., description="Number of characters, spaces included.")


class GitLogResponse(BaseModel):
    repository: str = Field(..., description="Repository folder inside the project ('' = the project folder).")
    commits: list[GitCommit] = Field(..., description="Newest first.")


class GitStatusResponse(BaseModel):
    repository: str = Field(..., description="Repository folder inside the project ('' = the project folder).")
    clean: bool = Field(..., description="True when no file is changed.")
    status: GitStatus

