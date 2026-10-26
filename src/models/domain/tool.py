"""Output contracts of the tools, one model per tool."""
from pydantic import BaseModel, Field

from models.domain.git import GitCommit, GitStatus
from models.domain.masking import MaskRepositoryName, MaskRepositoryNames


class ToolErrorResponse(BaseModel):
    """Returned instead of raising, so the agent can read the problem and retry."""
    error: str = Field(..., description="What went wrong and how to fix the call.")
    repositories: MaskRepositoryNames = Field(default_factory=list, description="The repositories the agent can use instead.")


class RunAutomationResponse(BaseModel):
    automation: str = Field(..., description="The automation started.")
    run_id: int = Field(..., description="Id of its run (Automation tab).")
    status: str = Field(..., description="'queued': the worker runs it in the background.")


class AutomationInfo(BaseModel):
    name: str
    description: str = Field("", description="What it does: read it to choose.")


class ListAutomationsResponse(BaseModel):
    automations: list[AutomationInfo] = Field(..., description="Active, with steps: the ones run_automation can start.")


class AutomationStepStatus(BaseModel):
    name: str
    status: str = Field(..., description="running, done, failed or skipped (its condition did not pass).")


class AutomationStatusResponse(BaseModel):
    """Only statuses: no output nor error messages (long, may hold secrets)."""
    automation: str
    run_id: int
    status: str = Field(..., description="queued, running, done or failed.")
    steps: list[AutomationStepStatus] = Field(..., description="The steps run so far, in order.")


class AgentTaskInfo(BaseModel):
    task: str = Field(..., description="The task's note name (agent-task-<title>.md): what delegate_task wants.")
    title: str
    status: str = Field(..., description="todo, in_progress or done.")


class ListAgentTasksResponse(BaseModel):
    tasks: list[AgentTaskInfo] = Field(..., description="The project's agent tasks.")


class DelegateTaskResponse(BaseModel):
    """The planning chat with Copilot is open: Copilot's questions are there, not here."""
    session_id: int = Field(..., description="The Copilot session: copilot_status wants it.")
    task: str
    repository: MaskRepositoryName = Field(..., description="Repository folder inside the project ('' = the project folder).")
    copilot_answered: bool = Field(..., description="Copilot read the task and answered (questions or a plan) in its chat.")
    chat: str = Field(..., description="Link to the Copilot chat in the app: give it to the user as a markdown link.")
    next_step: str = Field(..., description="What the user has to do now.")


class CopilotStatusResponse(BaseModel):
    """Only statuses: Copilot's messages and the diff are in the Copilot chat."""
    session_id: int
    task: str
    status: str = Field(..., description="planning (chat open, waiting for the user's ok), queued, running, done, failed or cancelled.")
    changed_files: int = Field(..., description="Files changed in the repository when the execution ended.")
    head_moved: bool = Field(..., description="True when a commit happened despite the rules: the user must check.")
    chat: str = Field(..., description="Link to the Copilot chat in the app.")


class ReadContextResponse(BaseModel):
    files: dict[str, str] = Field(..., description="File name -> its markdown content.")


class HelloWorldResponse(BaseModel):
    response: str = Field(..., description="The greeting message.")


class GitStatusResponse(BaseModel):
    repository: MaskRepositoryName = Field(..., description="Repository folder inside the project ('' = the project folder).")
    clean: bool = Field(..., description="True when no file is changed.")
    status: GitStatus



class GitPullResponse(BaseModel):
    repository: MaskRepositoryName = Field(..., description="Repository folder inside the project ('' = the project folder).")
    branch: str
    upstream: str
    updated: bool = Field(..., description="False when it was already up to date.")
    commits: list[GitCommit] = Field(..., description="The commits that arrived, newest first.")


class GitStashResponse(BaseModel):
    repository: MaskRepositoryName = Field(..., description="Repository folder inside the project ('' = the project folder).")
    stashed: bool = Field(..., description="False when there was nothing to put aside.")
    ref: str | None = Field(None, description="The new stash (stash@{0}).")
    message: str
    files: list[str] = Field(..., description="The tracked files put aside.")


class GitStashApplyResponse(BaseModel):
    repository: MaskRepositoryName = Field(..., description="Repository folder inside the project ('' = the project folder).")
    ref: str = Field(..., description="The stash applied; it stays in the stash list.")
    message: str
    applied: bool = Field(..., description="False when it left conflicts.")
    files: list[str] = Field(..., description="Files changed in the working tree after applying.")
    conflicts: list[str] = Field(..., description="Files left in conflict, to resolve by hand.")
