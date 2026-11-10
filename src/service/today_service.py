"""«📌 Oggi»: what needs the user in a project, computed by the app without LLM
(the panel at the top of the Attività tab, the secretary's tool ``today``):

- **waiting**: agent tasks created, in refinement or to verify; Copilot
  sessions waiting for the user (planning: Copilot's message is the last one;
  running: a question of ``ask_user`` without an answer);
- **overdue** / **due_soon**: items not done whose due date is past / within
  the project's ``due_soon_days`` (default 3), of activities not done;
- **to_close**: activities whose items are all done, not done themselves.

Two quick actions on an item, checked against its text (the panel shows a
number: the item may have changed meanwhile): ``check_item`` and ``set_due``."""
from datetime import date, timedelta

from core.error import ConflictError, ValidationError
from domain.project.data_paths import note_file_name
from models.domain.copilot import CopilotMessageRole, CopilotSessionStatus
from models.domain.note import ActivityStatus, TaskStatus
from models.domain.today import Today, TodayActivity, TodayItem, TodayWaiting, WaitingKind
from service.copilot_service import CopilotService
from service.project_data_service import ProjectDataService

_WAITING_STATUSES = (TaskStatus.CREATED, TaskStatus.REFINEMENT, TaskStatus.TO_VERIFY)


class TodayService:

    def __init__(self, project_data: ProjectDataService, copilot: CopilotService | None):
        """``copilot`` None (a run without Copilot): no session waits."""
        self._data = project_data
        self._copilot = copilot

    def today(self, project_name: str, today: date | None = None) -> Today:
        today = today or date.today()
        days = self._data.due_soon_days(project_name)
        tasks = self._data.agent_tasks(project_name)
        titles = {name: task.title for name, task in tasks}
        waiting = [TodayWaiting(kind=WaitingKind.TASK, task=name, title=task.title, status=task.status.value, session_id=None)
                   for name, task in sorted((pair for pair in tasks if pair[1].status in _WAITING_STATUSES),
                                            key=lambda pair: _WAITING_STATUSES.index(pair[1].status))]
        for session in self._copilot.sessions(project_name) if self._copilot else []:
            reason = self._copilot_waits(session.id, session.status) if session.id is not None else None
            if reason and session.task_note in titles:
                waiting.append(TodayWaiting(kind=WaitingKind.COPILOT, task=session.task_note, title=titles[session.task_note], status=reason,
                                            session_id=session.id))
        overdue, due_soon, to_close = [], [], []
        for name, activity in self._data.activities(project_name):
            if activity.status == ActivityStatus.DONE:
                continue
            if activity.items and all(item.done for item in activity.items):
                to_close.append(TodayActivity(activity=name, title=activity.title, items=len(activity.items)))
            for number, item in enumerate(activity.items, 1):
                if item.done or item.due is None:
                    continue
                entry = TodayItem(activity=name, activity_title=activity.title, item=number, text=item.text, due=item.due)
                if item.due < today:
                    overdue.append(entry)
                elif item.due <= today + timedelta(days=days):
                    due_soon.append(entry)
        return Today(date=today, due_soon_days=days, waiting=waiting, overdue=sorted(overdue, key=lambda entry: entry.due),
                     due_soon=sorted(due_soon, key=lambda entry: entry.due), to_close=to_close)

    def _copilot_waits(self, session_id: int, status: CopilotSessionStatus) -> str | None:
        """``answer`` (planning, Copilot spoke last), ``question`` (running, a question open), None otherwise."""
        assert self._copilot is not None
        if status == CopilotSessionStatus.RUNNING:
            return "question" if self._copilot.pending_question(session_id) else None
        if status != CopilotSessionStatus.PLANNING:
            return None
        messages = [message for message in self._copilot.messages(session_id) if message.role != CopilotMessageRole.EVENT]
        return "answer" if messages and messages[-1].role == CopilotMessageRole.COPILOT else None

    # ---------------------------------------------------------------- actions
    def check_item(self, project_name: str, activity_name: str, item: int, text: str) -> None:
        """The item done. ConflictError when it changed meanwhile (another text, gone, done already)."""
        activity, index = self._item(project_name, activity_name, item, text)
        if activity.items[index].done:
            raise ConflictError("La voce è già fatta.")
        self._replace(project_name, activity_name, activity, index, {"done": True})

    def set_due(self, project_name: str, activity_name: str, item: int, text: str, due: date) -> None:
        """The item's new due date («Rimanda»)."""
        activity, index = self._item(project_name, activity_name, item, text)
        self._replace(project_name, activity_name, activity, index, {"due": due})

    def _item(self, project_name: str, activity_name: str, item: int, text: str):
        activity = self._data.activity(project_name, note_file_name(activity_name))
        index = item - 1
        if not 0 <= index < len(activity.items):
            raise ValidationError(f"Voce {item} non trovata.")
        if activity.items[index].text != text:
            raise ConflictError("La voce è cambiata nel frattempo: ricarica.")
        return activity, index

    def _replace(self, project_name: str, activity_name: str, activity, index: int, update: dict) -> None:
        items = [*activity.items]
        items[index] = items[index].model_copy(update=update)
        self._data.save_activity(project_name, note_file_name(activity_name), activity.model_copy(update={"items": items}))
