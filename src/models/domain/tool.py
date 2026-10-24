"""Output contracts of the tools, one model per tool."""
from pydantic import BaseModel, Field

from models.domain.git import GitCommit, GitStatus


class ToolErrorResponse(BaseModel):
    """Returned instead of raising, so the agent can read the problem and retry."""
    error: str = Field(..., description="What went wrong and how to fix the call.")


class RunAutomationResponse(BaseModel):
    automation: str = Field(..., description="The automation started.")
    run_id: int = Field(..., description="Id of its run (Automation tab).")
    status: str = Field(..., description="'queued': the worker runs it in the background.")


class AutomationStepStatus(BaseModel):
    name: str
    status: str = Field(..., description="running, done, failed or skipped (its condition did not pass).")


class AutomationStatusResponse(BaseModel):
    """Only statuses: no output nor error messages (long, may hold secrets)."""
    automation: str
    run_id: int
    status: str = Field(..., description="queued, running, done or failed.")
    steps: list[AutomationStepStatus] = Field(..., description="The steps run so far, in order.")


class ReadContextResponse(BaseModel):
    files: dict[str, str] = Field(..., description="File name -> its markdown content.")


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


class GitStashApplyResponse(BaseModel):
    repository: str = Field(..., description="Repository folder inside the project ('' = the project folder).")
    ref: str = Field(..., description="The stash applied; it stays in the stash list.")
    message: str
    applied: bool = Field(..., description="False when it left conflicts.")
    files: list[str] = Field(..., description="Files changed in the working tree after applying.")
    conflicts: list[str] = Field(..., description="Files left in conflict, to resolve by hand.")
