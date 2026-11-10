"""today: the secretary's «📌 Oggi», the same numbers the panel shows, compact:
it answers «cosa c'è oggi?» with one call to data computed by the app."""
from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import TodayResponse, ToolErrorResponse
from service.today_service import TodayService
from tool.context import ToolContext
from tool.list.notes.activities import notes_run
from tool.spec import ToolSpec


def build(context: ToolContext) -> Tool:

    @tool(name="today", description=(
        "What needs the user today, already computed: agent tasks and Copilot sessions waiting, items overdue and due "
        "soon (activity, item, due date), activities whose items are all done. Use it for «cosa c'è oggi?», «a che punto sono?»."
    ))
    def today() -> TodayResponse | ToolErrorResponse:
        if not notes_run(context):
            return ToolErrorResponse(error="Disponibile solo nel chatbot di un progetto.")
        try:
            data = TodayService(context.require_project_data(), context.copilot).today(context.require_project())
        except AppError as exc:
            return ToolErrorResponse(error=str(exc))
        return TodayResponse(
            date=data.date.isoformat(),
            waiting=[f"{item.title} ({item.task}): " + ("Copilot aspetta una risposta" if item.kind == "copilot" else item.status)
                     for item in data.waiting],
            overdue=[f"{item.activity_title} · voce {item.item} «{item.text}» · scaduta il {item.due.isoformat()}" for item in data.overdue],
            due_soon=[f"{item.activity_title} · voce {item.item} «{item.text}» · scade il {item.due.isoformat()}" for item in data.due_soon],
            to_close=[f"{item.title} ({item.activity}): tutte le {item.items} voci fatte" for item in data.to_close],
            due_soon_days=data.due_soon_days,
        )

    return today


TODAY = ToolSpec(
    name="today", description="«📌 Oggi» del progetto: chi aspetta, voci scadute e in scadenza, attività da chiudere.", build=build,
    chatbot_only=True,
)
