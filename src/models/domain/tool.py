"""Output contracts of the tools, one model per tool."""
from pydantic import BaseModel, Field

from models.domain.git import GitBranch, GitBranchPullOutcome, GitCommit, GitDiffFile, GitStash, GitStatus
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
    status: str = Field(..., description="created, refinement (not ready yet), todo (ready to delegate), in_progress, "
                                         "to_verify (Copilot finished a development: the user checks it) or done.")
    type: str = Field(..., description="development, analysis, confluence (write a page) or jira (refine an issue).")
    copilot_status: str | None = Field(
        None, description="Status of the task's latest Copilot session (planning, queued, running, done, failed, cancelled); "
                          "null = never delegated, or Copilot not available.",
    )


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
    warning: str | None = Field(None, description="The task is not refined yet (created or in refinement): tell the user.")


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


class GitLogResponse(BaseModel):
    repository: MaskRepositoryName = Field(..., description="Repository folder inside the project ('' = the project folder).")
    commits: list[GitCommit] = Field(..., description="Newest first.")


class GitDiffResponse(BaseModel):
    repository: MaskRepositoryName = Field(..., description="Repository folder inside the project ('' = the project folder).")
    of: str = Field(..., description="What the diff shows: 'unstaged', 'staged' or 'commit <hash>'.")
    files: list[GitDiffFile] = Field(..., description="Every changed file, with lines added/deleted.")
    patch: str = Field(..., description="The unified diff.")
    truncated: bool = Field(..., description="True when the patch was cut: ask for a subfolder to see the rest.")
    untracked: list[str] = Field(..., description="New files not tracked by git: not in the patch.")


class GitFetchResponse(BaseModel):
    repository: MaskRepositoryName = Field(..., description="Repository folder inside the project ('' = the project folder).")
    branch: str | None = Field(..., description="Current branch; null = detached HEAD.")
    upstream: str | None
    ahead: int = Field(..., description="Commits to push.")
    behind: int = Field(..., description="Commits that arrived and are still to pull (git_pull_fast_forward).")


class GitBranchesResponse(BaseModel):
    repository: MaskRepositoryName = Field(..., description="Repository folder inside the project ('' = the project folder).")
    current: str | None = Field(..., description="Current branch; null = detached HEAD.")
    local: list[GitBranch] = Field(..., description="Local branches; upstream_gone = deleted on the remote.")
    remote: list[str] = Field(..., description="Remote-tracking branches as of the last fetch.")


class GitCheckoutResponse(BaseModel):
    repository: MaskRepositoryName = Field(..., description="Repository folder inside the project ('' = the project folder).")
    previous: str | None = Field(..., description="The branch before.")
    branch: str = Field(..., description="The branch now checked out.")
    created: bool = Field(..., description="True when a new local branch was created.")
    upstream: str | None


class GitCommitResponse(BaseModel):
    repository: MaskRepositoryName = Field(..., description="Repository folder inside the project ('' = the project folder).")
    branch: str
    commit: GitCommit
    files: list[str] = Field(..., description="The files in the commit.")


class GitPushResponse(BaseModel):
    repository: MaskRepositoryName = Field(..., description="Repository folder inside the project ('' = the project folder).")
    branch: str
    upstream: str
    upstream_created: bool = Field(..., description="True when the branch was pushed for the first time and now tracks it.")
    pushed: bool = Field(..., description="False when there was nothing to push.")
    commits: list[GitCommit] = Field(..., description="The commits sent, newest first.")


class GitStashListResponse(BaseModel):
    repository: MaskRepositoryName = Field(..., description="Repository folder inside the project ('' = the project folder).")
    stashes: list[GitStash] = Field(..., description="Newest first: stash@{0} is the latest.")


class GitPullAllResponse(BaseModel):
    branch: str
    repositories: list[GitBranchPullOutcome] = Field(
        ..., description="One per repository: status updated, up_to_date, skipped (reason says why) or failed.",
    )


class ActivityInfo(BaseModel):
    name: str = Field(..., description="The activity's note name (attivita-<title>.md): what the other activity tools want.")
    title: str
    status: str = Field(..., description="todo, in_progress or done.")
    done: int = Field(..., description="Items of its todo list done.")
    total: int = Field(..., description="All the items of its todo list.")
    agent_tasks: int = Field(..., description="How many agent tasks were born from it.")


class ListActivitiesResponse(BaseModel):
    today: str = Field(..., description="Today's date (YYYY-MM-DD), for due dates such as 'by Friday'.")
    activities: list[ActivityInfo] = Field(..., description="The project's activities.")


class TodoItemInfo(BaseModel):
    number: int = Field(..., description="Position in the todo list, from 1: what update_activity wants.")
    text: str
    done: bool
    priority: str | None = Field(None, description="high, medium or low.")
    due: str | None = Field(None, description="Due date, YYYY-MM-DD.")


class ActivityTaskInfo(BaseModel):
    task: str = Field(..., description="The agent task's note name.")
    title: str
    status: str = Field(..., description="created, refinement, todo, in_progress, to_verify or done.")


class ActivityResponse(BaseModel):
    """An activity without its references: the secretary does not read them."""
    name: str = Field(..., description="The activity's note name.")
    title: str
    status: str = Field(..., description="todo, in_progress or done.")
    description: str
    today: str = Field(..., description="Today's date (YYYY-MM-DD).")
    items: list[TodoItemInfo] = Field(..., description="Its todo list.")
    agent_tasks: list[ActivityTaskInfo] = Field(..., description="The agent tasks born from it (missing ones left out).")


class CreateCodeReferenceResponse(BaseModel):
    """What the scan of the todoMbarePilot comments did: counts and the note,
    never the comments nor the code (the user reads them in the note)."""
    note: str | None = Field(..., description="The code reference written; null = no comment found and no note to update.")
    created: bool = Field(..., description="True = a new note, false = the existing one rewritten.")
    files: int = Field(..., description="How many files have comments.")
    comments: int = Field(..., description="How many comments were found.")
    malformed: int = Field(0, description="Comments written wrong, not collected: listed in the note; tell the user to fix them.")
    link: str | None = Field(None, description="Link to the note in the app: give it to the user as a markdown link.")


class ReferenceInfo(BaseModel):
    """A reference by its title only: the secretary never reads the content."""
    name: str = Field(..., description="The reference's note name: what create_agent_task wants in references.")
    title: str
    kind: str = Field(..., description="code (a piece of code) or context (text, e.g. from Jira or Confluence).")


class ListReferencesResponse(BaseModel):
    references: list[ReferenceInfo] = Field(..., description="The project's references (titles only).")


class AgentTaskCreatedResponse(BaseModel):
    task: str = Field(..., description="The new task's note name (agent-task-<title>.md).")
    title: str
    type: str = Field(..., description="development, analysis, confluence or jira.")
    status: str = Field(..., description="Always refinement: the user refines it, then sets it to todo.")
    references: list[str] = Field(..., description="The linked references, by name.")
    activity: str | None = Field(None, description="The activity it is born from, linked to it; null = none.")
    link: str = Field(..., description="Link to the task in the app: give it to the user as a markdown link.")


class LinkedReferenceInfo(BaseModel):
    name: str
    title: str
    kind: str = Field(..., description="code or context.")
    source: str = Field(..., description="Where it was copied from (jira, confluence, todoMbarePilot...); '' = written by hand.")
    content: str


class AgentTaskDetailResponse(BaseModel):
    task: str
    title: str
    type: str = Field(..., description="development, analysis, confluence or jira.")
    status: str = Field(..., description="created, refinement, todo, in_progress, to_verify or done.")
    objective: str
    context: str
    criteria: list[str] = Field(..., description="Acceptance criteria, in order.")
    constraints: str
    references: list[LinkedReferenceInfo] = Field(..., description="The linked references with their content; missing ones are left out.")
    checklist: list[str] = Field([], description="What a refined task of this type should have: check it before proposing todo.")
    link: str = Field(..., description="Link to the task in the app.")
