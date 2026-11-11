"""The secretary's agent task tools: list the references by title, and create
an agent task (e.g. from an item of an activity's todo list), linked to that
activity when given. The task is born in
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
from tool.list.notes.activities import notes_run
from tool.spec import ToolSpec

_ONLY_IN_CHAT = "Agent task e riferimenti disponibili solo nel chatbot di un progetto."
_KINDS = {NoteType.CODE_REFERENCE: "code", NoteType.CONTEXT_REFERENCE: "context"}

Type = Annotated[TaskType, (
    "What the task asks for: development (change the code), analysis (analyse the code and answer), "
    "confluence (write a Confluence page) or jira (refine a Jira issue)."
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
        "Create an agent task, e.g. from an item of an activity's todo list: title, type, objective, context, acceptance "
        "criteria, constraints, the references to link (names from list_references) and the activity it is born from "
        "(it is linked to it) with the number of the item it comes from, if any (the item is checked by itself when the "
        "task is done). It is created in refinement: the user refines it and makes it ready. Write only what you "
        "know: leave a field empty rather than invent it."
    ))
    def create_agent_task(
        title: Annotated[str, "The task's title, short."],
        type: Type,
        objective: Annotated[str, "What the task must achieve; '' = not known yet."],
        context: Annotated[str, "Context: what is known around the task (where it comes from, decisions); '' = none."],
        criteria: Annotated[list[str], "Acceptance criteria, one per string; [] = none yet."],
        constraints: Annotated[str, "What must not be done or touched; '' = none."],
        references: References,
        activity: Annotated[str, "The activity it is born from (name from list_activities): it is linked to it; '' = none."],
        item: Annotated[int, "The number of the activity's item it comes from (from read_activity); 0 = none."] = 0,
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
            parent = note_file_name(activity.strip()) if activity.strip() else None
            if item and parent is None:
                return ToolErrorResponse(error="Per collegare una voce serve anche l'attività.")
            if parent is not None:
                born_from = project_data.activity(project_name, parent)  # exists, before creating the task
                if item:
                    project_data.item_index(born_from, item)
            task = AgentTask(
                title=title.strip(), status=TaskStatus.REFINEMENT, type=type, objective=objective.strip(),
                context=context.strip(), criteria=[ChecklistItem(text=text.strip()) for text in criteria if text.strip()],
                constraints=constraints.strip(), references=names,
            )
            name = project_data.create_agent_task(project_name, task)
            if parent is not None and item:
                project_data.link_item(project_name, parent, item, name)
            elif parent is not None:
                project_data.link_agent_task(project_name, parent, name)
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        return AgentTaskCreatedResponse(
            task=name, title=task.title, type=task.type.value, status=task.status.value, references=names, activity=parent, item=item or None,
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
