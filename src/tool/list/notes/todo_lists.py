"""The secretary's todo list tools: list, read, create a list, add items and tick
them. Never the references: the responses leave them out and the writes keep
the ones already linked. Nothing is deleted or renamed. Only in a chatbot's run."""
from datetime import date
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from domain.project.note_templates import parse_todo_item
from models.domain.agent import RunOrigin
from models.domain.note import TodoList
from models.domain.tool import ListTodoListsResponse, TodoItemInfo, TodoListInfo, TodoListResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.spec import ToolSpec

ListName = Annotated[str, "The list's note name (todo-list-<title>.md), as list_todo_lists gives it."]
Items = Annotated[list[str], (
    "New items, one per string: the text, optionally followed by two spaces and (priority, due date), "
    "e.g. 'Taggare il commit  (alta, 2026-10-30)'; priority alta, media or bassa; [] = none."
)]
Numbers = Annotated[list[int], "Item numbers (from 1, as read_todo_list gives them); [] = none."]

_ONLY_IN_CHAT = "Todo list disponibili solo nel chatbot di un progetto."


def notes_run(context: ToolContext) -> bool:
    """The notes tools work only here: a chatbot's run of a project."""
    return context.project_data is not None and context.project_name is not None and context.origin is RunOrigin.CHAT


def _response(name: str, todo: TodoList) -> TodoListResponse:
    return TodoListResponse(name=name, title=todo.title, today=date.today().isoformat(), items=[
        TodoItemInfo(number=number, text=item.text, done=item.done,
                     priority=item.priority.value if item.priority else None, due=item.due.isoformat() if item.due else None)
        for number, item in enumerate(todo.items, start=1)
    ])


def build_list(context: ToolContext) -> Tool:

    @tool(name="list_todo_lists", description="The project's todo lists, with how many items are done; also today's date.")
    def list_todo_lists() -> ListTodoListsResponse | ToolErrorResponse:
        if not notes_run(context):
            return ToolErrorResponse(error=_ONLY_IN_CHAT)
        project_data, project_name = context.require_project_data(), context.require_project()
        try:
            lists = project_data.todo_lists(project_name)
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        return ListTodoListsResponse(today=date.today().isoformat(), todo_lists=[
            TodoListInfo(name=name, title=todo.title, done=sum(item.done for item in todo.items), total=len(todo.items))
            for name, todo in lists
        ])

    return list_todo_lists


def build_read(context: ToolContext) -> Tool:

    @tool(name="read_todo_list", description="The items of a todo list, numbered, with done, priority and due date.")
    def read_todo_list(name: ListName) -> TodoListResponse | ToolErrorResponse:
        if not notes_run(context):
            return ToolErrorResponse(error=_ONLY_IN_CHAT)
        project_data, project_name = context.require_project_data(), context.require_project()
        try:
            return _response(name, project_data.todo_list(project_name, name))
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))

    return read_todo_list


def build_create(context: ToolContext) -> Tool:

    @tool(name="create_todo_list", description="Create a new todo list with its items; answers with the list as saved.")
    def create_todo_list(title: Annotated[str, "The list's title."], items: Items) -> TodoListResponse | ToolErrorResponse:
        if not notes_run(context):
            return ToolErrorResponse(error=_ONLY_IN_CHAT)
        project_data, project_name = context.require_project_data(), context.require_project()
        if not title.strip():
            return ToolErrorResponse(error="Serve un titolo.")
        try:
            todo = TodoList(title=title.strip(), items=[parse_todo_item(text) for text in items if text.strip()])
            name = project_data.create_todo_list(project_name, todo)
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        return _response(name, todo)

    return create_todo_list


def build_update(context: ToolContext) -> Tool:

    @tool(name="update_todo_list", description=(
        "Change an existing todo list: add items at the end, tick (check) or untick (uncheck) items by number. "
        "It cannot delete nor rename. Answers with the list as saved."
    ))
    def update_todo_list(name: ListName, add: Items, check: Numbers, uncheck: Numbers) -> TodoListResponse | ToolErrorResponse:
        if not notes_run(context):
            return ToolErrorResponse(error=_ONLY_IN_CHAT)
        project_data, project_name = context.require_project_data(), context.require_project()
        try:
            todo = project_data.todo_list(project_name, name)
            wrong = [number for number in (*check, *uncheck) if not 1 <= number <= len(todo.items)]
            if wrong:
                return ToolErrorResponse(error=f"Voci inesistenti: {', '.join(map(str, wrong))} (la lista ne ha {len(todo.items)}).")
            items = [
                item.model_copy(update={"done": True}) if number in check
                else item.model_copy(update={"done": False}) if number in uncheck else item
                for number, item in enumerate(todo.items, start=1)
            ]
            items += [parse_todo_item(text) for text in add if text.strip()]
            todo = todo.model_copy(update={"items": items})  # its references stay as they are
            project_data.save_todo_list(project_name, name, todo)
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        return _response(name, todo)

    return update_todo_list


LIST_TODO_LISTS = ToolSpec(
    name="list_todo_lists", description="Le todo list del progetto, con quante voci sono fatte.", build=build_list, chatbot_only=True,
)
READ_TODO_LIST = ToolSpec(
    name="read_todo_list", description="Le voci di una todo list (senza i riferimenti).", build=build_read, chatbot_only=True,
)
CREATE_TODO_LIST = ToolSpec(
    name="create_todo_list", description="Crea una todo list nuova con le sue voci.", build=build_create, chatbot_only=True,
)
UPDATE_TODO_LIST = ToolSpec(
    name="update_todo_list", description="Aggiunge voci a una todo list e le spunta o despunta; non cancella né rinomina.",
    build=build_update, chatbot_only=True,
)
