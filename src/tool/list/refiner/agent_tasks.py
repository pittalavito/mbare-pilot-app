"""The refiner's agent task tools: it takes a task only while it is created,
works on it while it is in refinement, and closes the refinement making it
todo. Every rule on the status is here, not in the prompt: nothing else can
be moved (todo, in_progress and done are not the refiner's). Title, type and
references stay the user's. The references' content reaches the agent through
the project's masking, as every tool output. Only in a chatbot's run of a project."""
from collections.abc import Callable
from typing import Annotated
from urllib.parse import quote

from datapizza.tools import Tool, tool

from core.error import AppError
from domain.project.data_paths import note_file_name
from domain.project.note_templates import STATUS_LABELS
from models.domain.note import AgentTask, ChecklistItem, NoteType, TaskStatus
from models.domain.tool import (
    AgentTaskDetailResponse,
    LinkedReferenceInfo,
    ListRefinableTasksResponse,
    RefinableTaskInfo,
    ToolErrorResponse,
)
from tool.context import ToolContext
from tool.list.notes.todo_lists import notes_run
from tool.spec import ToolSpec

_ONLY_IN_CHAT = "Agent task disponibili solo nel chatbot di un progetto."
_KINDS = {NoteType.CODE_REFERENCE: "code", NoteType.CONTEXT_REFERENCE: "context"}
_REFINABLE = (TaskStatus.CREATED, TaskStatus.REFINEMENT)

Task = Annotated[str, "The task's note name (agent-task-<title>.md), as list_refinable_tasks gives it."]


class _Refused(Exception):
    """A rule of the refiner broken: its message goes back to the agent."""


def _load(run: ToolContext, name: str, *allowed: TaskStatus) -> tuple[str, AgentTask]:
    """The task, when its status is one of ``allowed``; _Refused otherwise."""
    note = note_file_name(name.strip())
    task = run.require_project_data().agent_task(run.require_project(), note)
    if task.status not in allowed:
        wanted = " o ".join(f"«{STATUS_LABELS[status]}»" for status in allowed)
        raise _Refused(f"{note} è «{STATUS_LABELS[task.status]}»: si può fare solo con un task {wanted}.")
    return note, task


def _detail(run: ToolContext, note: str, task: AgentTask) -> AgentTaskDetailResponse:
    data, project = run.require_project_data(), run.require_project()
    references = []
    for name in task.references:
        try:
            kind, reference = data.reference(project, name)
        except AppError:
            continue  # removed by hand: left out
        references.append(LinkedReferenceInfo(name=name, title=reference.title, kind=_KINDS[kind], source=reference.source,
                                               content=reference.content))
    return AgentTaskDetailResponse(
        task=note, title=task.title, type=task.type.value, status=task.status.value, objective=task.objective, context=task.context,
        criteria=[item.text for item in task.criteria], constraints=task.constraints, references=references,
        link=f"/projects/{quote(project)}/data?note={quote(note)}",
    )


def _guarded[ResponseT](run: ToolContext, action: Callable[[], ResponseT]) -> ResponseT | ToolErrorResponse:
    """``action()``, with the run's checks and its errors as ToolErrorResponse."""
    if not notes_run(run):
        return ToolErrorResponse(error=_ONLY_IN_CHAT)
    try:
        return action()
    except (_Refused, AppError) as exc:
        return ToolErrorResponse(error=str(exc))


def build_list(run: ToolContext) -> Tool:

    @tool(name="list_refinable_tasks", description=(
        "The agent tasks you can work on: created (take one with start_refinement) or in refinement. "
        "The others (todo, in progress, done) are not yours."
    ))
    def list_refinable_tasks() -> ListRefinableTasksResponse | ToolErrorResponse:
        def action() -> ListRefinableTasksResponse:
            tasks = run.require_project_data().agent_tasks(run.require_project())
            return ListRefinableTasksResponse(tasks=[
                RefinableTaskInfo(task=name, title=task.title, type=task.type.value, status=task.status.value)
                for name, task in tasks if task.status in _REFINABLE
            ])
        return _guarded(run, action)

    return list_refinable_tasks


def build_start(run: ToolContext) -> Tool:

    @tool(name="start_refinement", description=(
        "Take a created agent task to refine it: it becomes in refinement. Only a created task; "
        "answers with the task, its references included."
    ))
    def start_refinement(task: Task) -> AgentTaskDetailResponse | ToolErrorResponse:
        def action() -> AgentTaskDetailResponse:
            note, current = _load(run, task, TaskStatus.CREATED)
            current = current.model_copy(update={"status": TaskStatus.REFINEMENT})
            run.require_project_data().save_agent_task(run.require_project(), note, current)
            return _detail(run, note, current)
        return _guarded(run, action)

    return start_refinement


def build_read(run: ToolContext) -> Tool:

    @tool(name="read_agent_task", description=(
        "An agent task in refinement with all its fields and the content of its linked references."
    ))
    def read_agent_task(task: Task) -> AgentTaskDetailResponse | ToolErrorResponse:
        def action() -> AgentTaskDetailResponse:
            note, current = _load(run, task, TaskStatus.REFINEMENT)
            return _detail(run, note, current)
        return _guarded(run, action)

    return read_agent_task


def build_update(run: ToolContext) -> Tool:

    @tool(name="update_agent_task", description=(
        "Write the fields of an agent task in refinement, after asking the user what you need. An empty value "
        "('' or []) leaves that field as it is; criteria, when given, replace all the acceptance criteria. "
        "Title, type and references are the user's. Answers with the task as saved."
    ))
    def update_agent_task(
        task: Task,
        objective: Annotated[str, "What the task must achieve; '' = unchanged."],
        context: Annotated[str, "What is known around the task: where it comes from, decisions; '' = unchanged."],
        criteria: Annotated[list[str], "All the acceptance criteria, one per string; [] = unchanged."],
        constraints: Annotated[str, "What must not be done or touched; '' = unchanged."],
    ) -> AgentTaskDetailResponse | ToolErrorResponse:
        def action() -> AgentTaskDetailResponse:
            note, current = _load(run, task, TaskStatus.REFINEMENT)
            changes: dict[str, object] = {key: value.strip() for key, value in
                             (("objective", objective), ("context", context), ("constraints", constraints)) if value.strip()}
            items = [text.strip() for text in criteria if text.strip()]
            if items:
                done = {item.text: item.done for item in current.criteria}
                changes["criteria"] = [ChecklistItem(text=text, done=done.get(text, False)) for text in items]
            current = current.model_copy(update=changes)
            run.require_project_data().save_agent_task(run.require_project(), note, current)
            return _detail(run, note, current)
        return _guarded(run, action)

    return update_agent_task


def build_finish(run: ToolContext) -> Tool:

    @tool(name="finish_refinement", description=(
        "Close the refinement: the task becomes todo, ready to delegate. Call it ONLY after the user said yes "
        "to it in their last message. Refused without an objective or acceptance criteria."
    ))
    def finish_refinement(task: Task) -> AgentTaskDetailResponse | ToolErrorResponse:
        def action() -> AgentTaskDetailResponse:
            note, current = _load(run, task, TaskStatus.REFINEMENT)
            missing = [label for label, empty in (("l'obiettivo", not current.objective.strip()),
                                                  ("i criteri di accettazione", not current.criteria)) if empty]
            if missing:
                raise _Refused(f"{note} non è ancora rifinito: mancano {' e '.join(missing)}.")
            current = current.model_copy(update={"status": TaskStatus.TODO})
            run.require_project_data().save_agent_task(run.require_project(), note, current)
            return _detail(run, note, current)
        return _guarded(run, action)

    return finish_refinement


LIST_REFINABLE_TASKS = ToolSpec(
    name="list_refinable_tasks", description="Gli agent task che il Refiner può prendere o sta rifinendo (creati o in rifinitura).",
    build=build_list, chatbot_only=True,
)
START_REFINEMENT = ToolSpec(
    name="start_refinement", description="Prende un agent task creato e lo porta in rifinitura.", build=build_start, chatbot_only=True,
)
READ_AGENT_TASK = ToolSpec(
    name="read_agent_task", description="Un agent task in rifinitura con il contenuto dei riferimenti collegati.",
    build=build_read, chatbot_only=True,
)
UPDATE_AGENT_TASK = ToolSpec(
    name="update_agent_task", description="Scrive obiettivo, contesto, criteri e vincoli di un agent task in rifinitura.",
    build=build_update, chatbot_only=True,
)
FINISH_REFINEMENT = ToolSpec(
    name="finish_refinement", description="Porta un agent task rifinito da «in rifinitura» a «da fare», con l'ok dell'utente.",
    build=build_finish, chatbot_only=True,
)
