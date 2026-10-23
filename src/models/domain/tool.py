"""Output contracts of the tools, one model per tool."""
from pydantic import BaseModel, Field

from models.domain.git import GitCommit, GitStatus


class ToolErrorResponse(BaseModel):
    """Returned instead of raising, so the agent can read the problem and retry."""
    error: str = Field(..., description="What went wrong and how to fix the call.")


class AskAgentResponse(BaseModel):
    agent: str = Field(..., description="The agent that answered.")
    run_id: str = Field(..., description="Its run, recorded on its own.")
    answer: str = Field(..., description="Its answer.")


class RunAutomationResponse(BaseModel):
    automation: str = Field(..., description="The automation started.")
    run_id: int = Field(..., description="Id of its run (Automation tab).")
    status: str = Field(..., description="'queued': the worker runs it in the background.")


class HelloWorldResponse(BaseModel):
    response: str = Field(..., description="The greeting message.")


class GitStatusResponse(BaseModel):
    repository: str = Field(..., description="Repository folder inside the project ('' = the project folder).")
    clean: bool = Field(..., description="True when no file is changed.")
    status: GitStatus



class GitPullResponse(BaseModel):
    repository: str = Field(..., description="Repository folder inside the project ('' = the project folder).")
    branch: str
    upstream: str
    updated: bool = Field(..., description="False when it was already up to date.")
    commits: list[GitCommit] = Field(..., description="The commits that arrived, newest first.")


class GitStashResponse(BaseModel):
    repository: str = Field(..., description="Repository folder inside the project ('' = the project folder).")
    stashed: bool = Field(..., description="False when there was nothing to put aside.")
    ref: str | None = Field(None, description="The new stash (stash@{0}).")
    message: str
    files: list[str] = Field(..., description="The tracked files put aside.")
