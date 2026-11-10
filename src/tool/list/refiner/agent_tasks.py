"""The refiner's agent task tools. They work only on the task open next to
the chat (``ToolContext.open_note``: no task name to pass, none other to
reach) and only while it is in refinement (the user's button moves it there
from created): read it, with the checklist of its type from the coding-agent
definition, write its fields, close the refinement making it todo. Every rule
on the status is here, not in the prompt: nothing else can be moved (todo and
what follows are not the refiner's). Title, type and references stay the
user's. The references' content reaches the agent through the project's
masking, as every tool output. Only in a chatbot's run of a project."""
from collections.abc import Callable
from typing import Annotated
from urllib.parse import quote

from datapizza.tools import Tool, tool

from core.error import AppError
from domain.project import coding_agent
from domain.project.data_paths import note_file_name, note_type
from domain.project.note_templates import STATUS_LABELS
from models.domain.note import AgentTask, ChecklistItem, NoteType, TaskStatus
from models.domain.tool import AgentTaskDetailResponse, LinkedReferenceInfo, ToolErrorResponse
from tool.context import ToolContext
from tool.list.notes.activities import notes_run
from tool.spec import ToolSpec

_ONLY_IN_CHAT = "Agent task disponibili solo nel chatbot di un progetto."
_KINDS = {NoteType.CODE_REFERENCE: "code", NoteType.CONTEXT_REFERENCE: "context"}
_NO_TASK = "Nessun agent task aperto accanto alla chat: chiedi all'utente di aprire il task da rifinire."
_PRESS_REFINE = "premi «Rifinisci con il Refiner» nel form del task per portarlo in rifinitura."


class _Refused(Exception):
    """A rule of the refiner broken: its message goes back to the agent."""


def _load(run: ToolContext) -> tuple[str, AgentTask]:
    """The open task, while in refinement; _Refused otherwise."""
    if not run.open_note or note_type(note_file_name(run.open_note)) != NoteType.AGENT_TASK:
        raise _Refused(_NO_TASK)
    note = note_file_name(run.open_note)
    task = run.require_project_data().agent_task(run.require_project(), note)
    if task.status != TaskStatus.REFINEMENT:
        hint = _PRESS_REFINE if task.status == TaskStatus.CREATED else "non è più tuo."
        raise _Refused(f"{note} è «{STATUS_LABELS[task.status]}», non «{STATUS_LABELS[TaskStatus.REFINEMENT]}»: {hint}")
    return note, task


def _checklist(run: ToolContext, task: AgentTask) -> list[str]:
    """What a refined task of its type should have; [] when the definition has none (or cannot be read)."""
    if run.copilot is None:
        return []
    try:
        return coding_agent.task_checklist(run.copilot.coding_agent(run.require_project()), task.type)
    except AppError:
        return []


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
        checklist=_checklist(run, task), link=f"/projects/{quote(project)}/data?note={quote(note)}",
    )


def _guarded[ResponseT](run: ToolContext, action: Callable[[], ResponseT]) -> ResponseT | ToolErrorResponse:
    """``action()``, with the run's checks and its errors as ToolErrorResponse."""
    if not notes_run(run):
        return ToolErrorResponse(error=_ONLY_IN_CHAT)
    try:
        return action()
    except (_Refused, AppError) as exc:
        return ToolErrorResponse(error=str(exc))


def build_read(run: ToolContext) -> Tool:

    @tool(name="read_agent_task", description=(
        "The agent task open next to the chat (only while in refinement) with all its fields, the content of its "
        "linked references and the checklist of its type: what a refined task should have."
    ))
    def read_agent_task() -> AgentTaskDetailResponse | ToolErrorResponse:
        def action() -> AgentTaskDetailResponse:
            note, current = _load(run)
            return _detail(run, note, current)
        return _guarded(run, action)

    return read_agent_task


def build_update(run: ToolContext) -> Tool:

    @tool(name="update_agent_task", description=(
        "Write the fields of the agent task open next to the chat, after asking the user what you need. An empty value "
        "('' or []) leaves that field as it is; criteria, when given, replace all the acceptance criteria. "
        "Title, type and references are the user's. Answers with the task as saved."
    ))
    def update_agent_task(
        objective: Annotated[str, "What the task must achieve; '' = unchanged."],
        context: Annotated[str, "What is known around the task: where it comes from, decisions; '' = unchanged."],
        criteria: Annotated[list[str], "All the acceptance criteria, one per string; [] = unchanged."],
        constraints: Annotated[str, "What must not be done or touched; '' = unchanged."],
    ) -> AgentTaskDetailResponse | ToolErrorResponse:
        def action() -> AgentTaskDetailResponse:
            note, current = _load(run)
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
        "Close the refinement of the agent task open next to the chat: it becomes todo, ready to delegate. Call it "
        "ONLY after the user said yes to it in their last message. Refused without an objective or acceptance criteria."
    ))
    def finish_refinement() -> AgentTaskDetailResponse | ToolErrorResponse:
        def action() -> AgentTaskDetailResponse:
            note, current = _load(run)
            missing = [label for label, empty in (("l'obiettivo", not current.objective.strip()),
                                                  ("i criteri di accettazione", not current.criteria)) if empty]
            if missing:
                raise _Refused(f"{note} non è ancora rifinito: mancano {' e '.join(missing)}.")
            current = current.model_copy(update={"status": TaskStatus.TODO})
            run.require_project_data().save_agent_task(run.require_project(), note, current)
            return _detail(run, note, current)
        return _guarded(run, action)

    return finish_refinement


READ_AGENT_TASK = ToolSpec(
    name="read_agent_task", description="L'agent task aperto (in rifinitura) con i riferimenti collegati e la checklist del suo tipo.",
    build=build_read, chatbot_only=True,
)
UPDATE_AGENT_TASK = ToolSpec(
    name="update_agent_task", description="Scrive obiettivo, contesto, criteri e vincoli dell'agent task aperto (in rifinitura).",
    build=build_update, chatbot_only=True,
)
FINISH_REFINEMENT = ToolSpec(
    name="finish_refinement", description="Porta l'agent task aperto da «in rifinitura» a «da fare», con l'ok dell'utente.",
    build=build_finish, chatbot_only=True,
)
