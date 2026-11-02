"""The secretary's agent task tools: list the references by title, and create
an agent task (e.g. from an item of a todo list). The task is born in
refinement: the user refines it and sets it to todo. The secretary never
reads a reference's content, only its title, to choose which ones to link.
Only in a chatbot's run of a project."""
from typing import Annotated
from urllib.parse import quote

from datapizza.tools import Tool, tool

from core.error import AppError
from domain.project.data_paths import note_file_name
from models.domain.note import AgentTask, ChecklistItem, NoteType, TaskStatus, TaskType
from models.domain.tool import AgentTaskCreatedResponse, ListReferencesResponse, ReferenceInfo, ToolErrorResponse
from tool.context import ToolContext
from tool.list.notes.todo_lists import notes_run
from tool.spec import ToolSpec

_ONLY_IN_CHAT = "Agent task e riferimenti disponibili solo nel chatbot di un progetto."
_KINDS = {NoteType.CODE_REFERENCE: "code", NoteType.CONTEXT_REFERENCE: "context"}

Type = Annotated[TaskType, (
    "What the task asks for: refinement (refine a story), development (develop something) or analysis (analyse and answer)."
)]
References = Annotated[list[str], "Reference note names from list_references (only ones that matter for the task); [] = none."]


def build_list_references(context: ToolContext) -> Tool:

    @tool(name="list_references", description=(
        "The project's references (code and context) by name and title only, never their content: "
        "to choose which ones to link when creating an agent task."
    ))
    def list_references() -> ListReferencesResponse | ToolErrorResponse:
        if not notes_run(context):
            return ToolErrorResponse(error=_ONLY_IN_CHAT)
        try:
            references = context.require_project_data().references(context.require_project())
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        return ListReferencesResponse(references=[
            ReferenceInfo(name=name, title=reference.title, kind=_KINDS[kind]) for name, kind, reference in references
        ])

    return list_references


def build_create(run: ToolContext) -> Tool:

    @tool(name="create_agent_task", description=(
        "Create an agent task, e.g. from an item of a todo list: title, type, objective, context, acceptance criteria, "
        "constraints and the references to link (names from list_references). It is created in refinement: the user "
        "refines it and makes it ready. Write only what you know: leave a field empty rather than invent it."
    ))
    def create_agent_task(
        title: Annotated[str, "The task's title, short."],
        type: Type,
        objective: Annotated[str, "What the task must achieve; '' = not known yet."],
        context: Annotated[str, "Context: what is known around the task (where it comes from, decisions); '' = none."],
        criteria: Annotated[list[str], "Acceptance criteria, one per string; [] = none yet."],
        constraints: Annotated[str, "What must not be done or touched; '' = none."],
        references: References,
    ) -> AgentTaskCreatedResponse | ToolErrorResponse:
        if not notes_run(run):
            return ToolErrorResponse(error=_ONLY_IN_CHAT)
        project_data, project_name = run.require_project_data(), run.require_project()
        if not title.strip():
            return ToolErrorResponse(error="Serve un titolo.")
        try:
            known = {name for name, _, _ in project_data.references(project_name)}
            names = list(dict.fromkeys(note_file_name(name.strip()) for name in references if name.strip()))
            unknown = [name for name in names if name not in known]
            if unknown:
                return ToolErrorResponse(error=f"Riferimenti inesistenti: {', '.join(unknown)}. Usa i nomi che dà list_references.")
            task = AgentTask(
                title=title.strip(), status=TaskStatus.REFINEMENT, type=type, objective=objective.strip(),
                context=context.strip(), criteria=[ChecklistItem(text=text.strip()) for text in criteria if text.strip()],
                constraints=constraints.strip(), references=names,
            )
            name = project_data.create_agent_task(project_name, task)
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        return AgentTaskCreatedResponse(
            task=name, title=task.title, type=task.type.value, status=task.status.value, references=names,
            link=f"/projects/{quote(project_name)}/data?note={quote(name)}",
        )

    return create_agent_task


LIST_REFERENCES = ToolSpec(
    name="list_references", description="I riferimenti del progetto, solo nome e titolo (mai il contenuto).",
    build=build_list_references, chatbot_only=True,
)
CREATE_AGENT_TASK = ToolSpec(
    name="create_agent_task", description="Crea un agent task (in rifinitura), con i riferimenti scelti per titolo.",
    build=build_create, chatbot_only=True,
)
