"""The secretary's activity tools: list and read the activities, create one
with its description and todo list, change its description and status, add
items and tick them. Never the references: the responses leave them out and
the writes keep the ones already linked (and the agent tasks born from it).
Nothing is deleted or renamed. Only in a chatbot's run of a project."""
from datetime import date
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from domain.project.note_templates import parse_todo_item
from models.domain.agent import RunOrigin
from models.domain.note import Activity, ActivityStatus
from models.domain.tool import (
    ActivityInfo,
    ActivityResponse,
    ActivityTaskInfo,
    ListActivitiesResponse,
    TodoItemInfo,
    ToolErrorResponse,
)
from tool.context import ToolContext
from tool.spec import ToolSpec

ActivityName = Annotated[str, "The activity's note name (attivita-<title>.md), as list_activities gives it."]
Items = Annotated[list[str], (
    "New items of its todo list, one per string: the text, optionally followed by two spaces and (priority, due date), "
    "e.g. 'Taggare il commit  (alta, 2026-10-30)'; priority alta, media or bassa; [] = none."
)]
Numbers = Annotated[list[int], "Item numbers (from 1, as read_activity gives them); [] = none."]

_ONLY_IN_CHAT = "Attività disponibili solo nel chatbot di un progetto."


def notes_run(context: ToolContext) -> bool:
    """The notes tools work only here: a chatbot's run of a project."""
    return context.project_data is not None and context.project_name is not None and context.origin is RunOrigin.CHAT


def _response(context: ToolContext, name: str, activity: Activity) -> ActivityResponse:
    tasks = []
    for task_name in activity.agent_tasks:
        try:
            task = context.require_project_data().agent_task(context.require_project(), task_name)
        except AppError:
            continue  # deleted by hand
        tasks.append(ActivityTaskInfo(task=task_name, title=task.title, status=task.status.value))
    return ActivityResponse(
        name=name, title=activity.title, status=activity.status.value, description=activity.description,
        today=date.today().isoformat(), agent_tasks=tasks, items=[
            TodoItemInfo(number=number, text=item.text, done=item.done,
                         priority=item.priority.value if item.priority else None, due=item.due.isoformat() if item.due else None)
            for number, item in enumerate(activity.items, start=1)
        ],
    )


def build_list(context: ToolContext) -> Tool:

    @tool(name="list_activities", description=(
        "The project's activities with their status, how many items of their todo list are done and how many "
        "agent tasks were born from them; also today's date."
    ))
    def list_activities() -> ListActivitiesResponse | ToolErrorResponse:
        if not notes_run(context):
            return ToolErrorResponse(error=_ONLY_IN_CHAT)
        try:
            activities = context.require_project_data().activities(context.require_project())
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        return ListActivitiesResponse(today=date.today().isoformat(), activities=[
            ActivityInfo(name=name, title=activity.title, status=activity.status.value, done=sum(item.done for item in activity.items),
                         total=len(activity.items), agent_tasks=len(activity.agent_tasks))
            for name, activity in activities
        ])

    return list_activities


def build_read(context: ToolContext) -> Tool:

    @tool(name="read_activity", description=(
        "An activity: status, description, its todo list (numbered, with done, priority and due date) and the agent "
        "tasks born from it."
    ))
    def read_activity(name: ActivityName) -> ActivityResponse | ToolErrorResponse:
        if not notes_run(context):
            return ToolErrorResponse(error=_ONLY_IN_CHAT)
        try:
            return _response(context, name, context.require_project_data().activity(context.require_project(), name))
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))

    return read_activity


def build_create(context: ToolContext) -> Tool:

    @tool(name="create_activity", description=(
        "Create a new activity (to do) with its description and the items of its todo list; answers with it as saved."
    ))
    def create_activity(
        title: Annotated[str, "The activity's title."],
        description: Annotated[str, "What the activity is about; '' = none yet."],
        items: Items,
    ) -> ActivityResponse | ToolErrorResponse:
        if not notes_run(context):
            return ToolErrorResponse(error=_ONLY_IN_CHAT)
        project_data, project_name = context.require_project_data(), context.require_project()
        if not title.strip():
            return ToolErrorResponse(error="Serve un titolo.")
        try:
            activity = Activity(title=title.strip(), description=description.strip(),
                                items=[parse_todo_item(text) for text in items if text.strip()])
            name = project_data.create_activity(project_name, activity)
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        return _response(context, name, activity)

    return create_activity


def build_update(context: ToolContext) -> Tool:

    @tool(name="update_activity", description=(
        "Change an existing activity: its description and status, add items at the end of its todo list, tick (check) "
        "or untick (uncheck) items by number. An empty value leaves that part as it is. It cannot delete nor rename. "
        "Answers with the activity as saved."
    ))
    def update_activity(
        name: ActivityName,
        description: Annotated[str, "The new description, replacing the old one; '' = unchanged."],
        status: Annotated[str, "todo, in_progress or done; '' = unchanged."],
        add: Items,
        check: Numbers,
        uncheck: Numbers,
    ) -> ActivityResponse | ToolErrorResponse:
        if not notes_run(context):
            return ToolErrorResponse(error=_ONLY_IN_CHAT)
        project_data, project_name = context.require_project_data(), context.require_project()
        if status.strip() and status.strip() not in {item.value for item in ActivityStatus}:
            return ToolErrorResponse(error=f"Stato non valido: {status!r} (todo, in_progress o done).")
        try:
            activity = project_data.activity(project_name, name)
            wrong = [number for number in (*check, *uncheck) if not 1 <= number <= len(activity.items)]
            if wrong:
                return ToolErrorResponse(error=f"Voci inesistenti: {', '.join(map(str, wrong))} (la todo list ne ha {len(activity.items)}).")
            items = [
                item.model_copy(update={"done": True}) if number in check
                else item.model_copy(update={"done": False}) if number in uncheck else item
                for number, item in enumerate(activity.items, start=1)
            ]
            items += [parse_todo_item(text) for text in add if text.strip()]
            changes: dict[str, object] = {"items": items}  # references and agent tasks stay as they are
            if description.strip():
                changes["description"] = description.strip()
            if status.strip():
                changes["status"] = ActivityStatus(status.strip())
            activity = activity.model_copy(update=changes)
            project_data.save_activity(project_name, name, activity)
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        return _response(context, name, activity)

    return update_activity


LIST_ACTIVITIES = ToolSpec(
    name="list_activities", description="Le attività del progetto, con stato e quante voci sono fatte.", build=build_list, chatbot_only=True,
)
READ_ACTIVITY = ToolSpec(
    name="read_activity", description="Un'attività: stato, descrizione, todo list e agent task nati da lei (senza i riferimenti).",
    build=build_read, chatbot_only=True,
)
CREATE_ACTIVITY = ToolSpec(
    name="create_activity", description="Crea un'attività nuova con descrizione e todo list.", build=build_create, chatbot_only=True,
)
UPDATE_ACTIVITY = ToolSpec(
    name="update_activity", description="Cambia descrizione e stato di un'attività, aggiunge voci e le spunta; non cancella né rinomina.",
    build=build_update, chatbot_only=True,
)
