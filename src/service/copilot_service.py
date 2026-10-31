"""Agent tasks delegated to GitHub Copilot CLI (models/domain/copilot.py).

A session lives in two phases:

1. **Planning** (in the API, while the user waits): the first turn gives
   Copilot the task and asks it to read the code, ask its questions and
   propose a plan; then the user and Copilot chat. Plan mode: nothing changes.
2. **Execution** (in the worker, after ``approve``): the same Copilot session
   resumes in autopilot and changes the files, minus the denied tools (no
   commits). HEAD is read before and after: if it moved, the session says so
   (nothing is undone: that is the user's call).

The prompts and the denied tools come from the coding-agent definition in the
data folder (domain/project/coding_agent.py), read at every use.

One execution at a time per repository (the queue waits); after an execution
the chat can go on and a new ok starts a new one. The task's status follows:
in progress while it runs, done when it succeeds, back to todo otherwise."""
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from config import Config
from core.error import AppError, ConflictError, NotFoundError, UpstreamError, ValidationError
from core.observability import LogPrefix, log_exception, observed
from domain.client.copilot.client import NOT_FOUND, CopilotClient, CopilotMode
from domain.project import coding_agent
from domain.project.data_paths import note_file_name
from models.domain.copilot import (
    CodingAgentSettings,
    CopilotMessage,
    CopilotMessageRole,
    CopilotModel,
    CopilotModelUsage,
    CopilotPhase,
    CopilotSession,
    CopilotSessionStatus,
    CopilotTurn,
    CopilotTurnRecord,
    CopilotUsage,
)
from models.domain.note import TaskStatus
from service.git_service import GitService
from service.project_data_service import ProjectDataService
from service.store.copilot_store import CopilotStore
from service.store_service import StoreService

_CANCEL_CHECK_SECONDS = 2.0


def _short(commit: str) -> str:
    return commit[:8] or "nessun commit"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CopilotService:

    def __init__(
        self,
        store_service: StoreService,
        copilot: CopilotStore,
        git_service: GitService,
        project_data_service: ProjectDataService,
        client: CopilotClient,
        planning_timeout_seconds: float,
        execution_timeout_seconds: float,
    ):
        self._store = store_service
        self._copilot = copilot
        self._git = git_service
        self._data = project_data_service
        self._client = client
        self._planning_timeout = planning_timeout_seconds
        self._execution_timeout = execution_timeout_seconds

    @classmethod
    def from_config(cls, store_service: StoreService, copilot: CopilotStore, git_service: GitService,
                    project_data_service: ProjectDataService) -> "CopilotService":
        """The CLI, model, token and timeouts from the Config (COPILOT_*).
        ``git_service`` resolves the repository folder and reads HEAD and
        ``git status`` around an execution (moved HEAD, changed files)."""
        config = Config.get()
        token = config.copilot_github_token.get_secret_value() if config.copilot_github_token else None
        return cls(
            store_service=store_service,
            copilot=copilot,
            git_service=git_service,
            project_data_service=project_data_service,
            client=CopilotClient(config.copilot_command, config.copilot_model, token),
            planning_timeout_seconds=config.copilot_planning_timeout_minutes * 60,
            execution_timeout_seconds=config.copilot_execution_timeout_minutes * 60,
        )

    # ------------------------------------------------------------------ read
    def version(self) -> str | None:
        """The installed Copilot CLI, None when missing."""
        return self._client.version()

    def coding_agent(self, project_name: str | None = None) -> CodingAgentSettings:
        """Prompts and denied tools: the global definition, with the project's
        fields over it. Raises ValidationError when missing or broken."""
        return coding_agent.load(self._store, project_name)

    def model_options(self, settings: CodingAgentSettings) -> list[tuple[CopilotModel, CopilotModelUsage | None]]:
        """The definition's models, the cheapest first (input + output price;
        those without a price last, in the file's order), each with what it
        used so far in every project (None = never used)."""
        used = {item.model: item for item in self._copilot.usage_by_model()}
        ordered = sorted(settings.models, key=lambda model: (model.price is None, model.price.input + model.price.output if model.price else 0.0))
        return [(model, used.get(model.name)) for model in ordered]

    @property
    def default_model(self) -> str:
        """COPILOT_MODEL; ``""`` = Copilot's own default."""
        return self._client.model

    def coding_agent_or_error(self, project_name: str | None = None) -> tuple[CodingAgentSettings | None, str | None]:
        """The definition, or why Copilot cannot start with the current files."""
        try:
            return self.coding_agent(project_name), None
        except AppError as exc:
            return None, str(exc)

    def sessions(self, project_name: str) -> list[CopilotSession]:
        """A project's sessions, newest first."""
        return self._copilot.list_sessions(project_name)

    def session(self, session_id: int) -> CopilotSession:
        session = self._copilot.get_session(session_id)
        if session is None:
            raise NotFoundError(f"Sessione Copilot non trovata: {session_id}")
        return session

    def messages(self, session_id: int) -> list[CopilotMessage]:
        return self._copilot.list_messages(self.session(session_id).id)

    # ----------------------------------------------------------------- usage
    def session_turns(self, session_id: int) -> list[CopilotTurnRecord]:
        """What each turn of the session used, oldest first."""
        return self._copilot.list_session_turns(self.session(session_id).id)

    def recent_turns(self, limit: int = 100, project_name: str | None = None) -> list[CopilotTurnRecord]:
        """Every session's turns, newest first (also of deleted sessions)."""
        return self._copilot.list_turns(limit, project_name)

    def usage_by_model(self, days: int | None = None, project_name: str | None = None) -> list[CopilotModelUsage]:
        """Totals per model over the last ``days`` (None = ever), the most AI credits first."""
        since = _now() - timedelta(days=days) if days else None
        return self._copilot.usage_by_model(since, project_name)

    # -------------------------------------------------------------- planning
    @observed(LogPrefix.COPILOT_SERVICE)
    def start(self, project_name: str, task_note: str, repository: str = "", prompt: str = "", model: str = "") -> CopilotSession:
        """A new session on an agent task: the first planning turn runs now,
        so the session comes back with Copilot's questions (or the error).
        ``prompt``: one of the definition's prompts (``""`` = ``plan_prompt``);
        ``model``: one of its models (``""`` = the default), for every turn."""
        if not self._client.available:
            raise UpstreamError(NOT_FOUND)
        settings = self.coding_agent(project_name)
        model = coding_agent.check_model(settings, model)
        task = self._data.agent_task(project_name, task_note)  # exists and is an agent task
        folder = self._git.repository_folder(project_name, repository)
        first_turn = coding_agent.plan_prompt(settings, self._data.read_note(project_name, task_note), prompt.strip())
        session_id = str(uuid4())
        if task.references and (note := coding_agent.references_note(settings, self._data.copilot_folder(project_name, task_note, session_id))):
            first_turn += f"\n\n{note}"
        session = self._copilot.save_session(CopilotSession(
            project_name=project_name,
            task_note=task_note,
            repository=repository.strip().strip("/\\"),
            copilot_session_id=session_id,
            prompt=prompt.strip(),
            model=model,
        ))
        return self._plan_turn(session, folder, first_turn)

    @observed(LogPrefix.COPILOT_SERVICE)
    def send(self, session_id: int, text: str) -> CopilotSession:
        """A message of the planning chat and Copilot's answer. After an
        execution the chat goes on: the session is back to planning."""
        session = self.session(session_id)
        if session.status in (CopilotSessionStatus.QUEUED, CopilotSessionStatus.RUNNING):
            raise ConflictError("Copilot sta eseguendo il task: aspetta che finisca o annulla.")
        if not text.strip():
            raise ValidationError("Il messaggio è vuoto.")
        folder = self._git.repository_folder(session.project_name, session.repository)
        return self._plan_turn(session, folder, text.strip())

    def _plan_turn(self, session: CopilotSession, folder: Path, prompt: str) -> CopilotSession:
        self._message(session, CopilotMessageRole.USER, prompt)
        session = self._update(session, status=CopilotSessionStatus.PLANNING, error=None)
        started = time.monotonic()
        turn = self._client.turn(folder, session.copilot_session_id, prompt, CopilotMode.PLAN, self._planning_timeout, model=session.model,
                                 extra_dirs=self._task_folder(session))
        self._record_usage(session, turn, CopilotPhase.PLAN, started)
        return self._record(session, turn)

    @observed(LogPrefix.COPILOT_SERVICE)
    def approve(self, session_id: int) -> CopilotSession:
        """The user's ok: the execution goes in the worker's queue. Files
        already changed in the repository are listed, as a warning."""
        session = self.session(session_id)
        if session.status != CopilotSessionStatus.PLANNING:
            raise ConflictError("Si può dare l'ok solo durante la preparazione.")
        if not any(message.role == CopilotMessageRole.COPILOT for message in self._copilot.list_messages(session.id)):
            raise ConflictError("Copilot non ha ancora risposto: aspetta la sua risposta prima di dare l'ok.")
        changed = self._changed_files(session)
        if changed:
            listed = "\n".join(f"- {path}" for path in changed[:20]) + ("\n- …" if len(changed) > 20 else "")
            self._message(session, CopilotMessageRole.EVENT,
                          f"⚠️ Nel repository ci sono già {len(changed)} file modificati: le modifiche di Copilot si aggiungeranno a queste.\n{listed}")
        self._message(session, CopilotMessageRole.EVENT, "In coda: parte appena il worker è libero (un'esecuzione alla volta per repository).")
        return self._update(session, status=CopilotSessionStatus.QUEUED, cancel_requested=False, error=None)

    @observed(LogPrefix.COPILOT_SERVICE)
    def cancel(self, session_id: int) -> CopilotSession:
        """A queued execution never starts; a running one is stopped by the worker."""
        session = self.session(session_id)
        if session.status == CopilotSessionStatus.QUEUED:
            self._message(session, CopilotMessageRole.EVENT, "Annullata prima di partire.")
            return self._update(session, status=CopilotSessionStatus.CANCELLED, finished_at=_now())
        if session.status == CopilotSessionStatus.RUNNING:
            self._message(session, CopilotMessageRole.EVENT, "Annullamento richiesto: il worker ferma Copilot.")
            return self._update(session, cancel_requested=True)
        raise ConflictError("Non c'è un'esecuzione da annullare.")

    @observed(LogPrefix.COPILOT_SERVICE)
    def delete(self, session_id: int) -> None:
        """With its messages; the files Copilot changed stay. Copilot's own session stays in its folder."""
        session = self.session(session_id)
        if session.status in (CopilotSessionStatus.QUEUED, CopilotSessionStatus.RUNNING):
            raise ConflictError("La sessione è in coda o in esecuzione: annullala prima.")
        self._copilot.delete_session(session.id)
        self._data.delete_copilot_folder(session.project_name, session.copilot_session_id)

    @observed(LogPrefix.COPILOT_SERVICE)
    def delete_task_sessions(self, project_name: str, task_note: str) -> int:
        """Every session of an agent task (e.g. before deleting the task), with
        their messages; none if one of them is queued or running. The usage of
        their turns stays in Observability. Returns how many were deleted."""
        name = note_file_name(task_note)
        sessions = [session for session in self._copilot.list_sessions(project_name) if note_file_name(session.task_note) == name]
        if any(session.status in (CopilotSessionStatus.QUEUED, CopilotSessionStatus.RUNNING) for session in sessions):
            raise ConflictError("Una sessione di questo task è in coda o in esecuzione: annullala prima.")
        for session in sessions:
            self._copilot.delete_session(session.id)
            self._data.delete_copilot_folder(project_name, session.copilot_session_id)
        return len(sessions)

    # ---------------------------------------------------------------- worker
    def run_next(self, on_claim: Callable[[CopilotSession], None] | None = None) -> CopilotSession | None:
        """Execute the next queued session whose repository is free; None when there is none."""
        session = self._copilot.claim_next_session()
        if session is None:
            return None
        if on_claim:
            on_claim(session)
        try:
            settings = self.coding_agent(session.project_name)
            folder = self._git.repository_folder(session.project_name, session.repository)
            head_before = self._git.head(session.project_name, session.repository)
        except AppError as exc:
            self._message(session, CopilotMessageRole.EVENT, f"❌ Non partita: {exc}")
            return self._update(session, status=CopilotSessionStatus.FAILED, error=str(exc), finished_at=_now())
        session = self._update(session, head_before=head_before, head_after=None, changed_files=[], error=None)
        self._message(session, CopilotMessageRole.EVENT, "▶️ Esecuzione partita: Copilot modifica i file, senza commit.")
        self._set_task_status(session, TaskStatus.IN_PROGRESS)
        self._message(session, CopilotMessageRole.USER, settings.execute_prompt)
        started = time.monotonic()
        turn = self._client.turn(folder, session.copilot_session_id, settings.execute_prompt, CopilotMode.EXECUTE,
                                 self._execution_timeout, settings.denied_tools, self._cancel_check(session.id), model=session.model,
                                 extra_dirs=self._task_folder(session))
        self._record_usage(session, turn, CopilotPhase.EXECUTE, started)
        session = self._record(session, turn)
        return self._finish(session, turn)

    def fail_interrupted(self) -> int:
        """At the worker's start: the executions left ``running`` by a worker that died."""
        sessions = self._copilot.list_sessions_by_status(CopilotSessionStatus.RUNNING)
        for session in sessions:
            self._message(session, CopilotMessageRole.EVENT, "❌ Interrotta: il worker si è fermato durante l'esecuzione.")
            self._update(session, status=CopilotSessionStatus.FAILED, error="Worker interrotto.", finished_at=_now())
            self._set_task_status(session, TaskStatus.TODO)
        return len(sessions)

    def _finish(self, session: CopilotSession, turn: CopilotTurn) -> CopilotSession:
        head_after, changed = None, []
        try:
            head_after = self._git.head(session.project_name, session.repository)
            changed = self._changed_files(session)
        except AppError:
            log_exception(LogPrefix.COPILOT_SERVICE, "Stato git non letto a fine esecuzione")
        status = (
            CopilotSessionStatus.CANCELLED if turn.cancelled
            else CopilotSessionStatus.FAILED if turn.error else CopilotSessionStatus.DONE
        )
        session = self._update(session, status=status, head_after=head_after, changed_files=changed,
                               cancel_requested=False, finished_at=_now())
        if session.head_moved:
            self._message(session, CopilotMessageRole.EVENT,
                          f"⚠️ L'HEAD è cambiato durante l'esecuzione ({_short(session.head_before)} → {_short(session.head_after)}): "
                          "un commit o un'altra operazione git non autorizzata. Controlla prima di continuare: non ho annullato niente.")
        summary = {CopilotSessionStatus.DONE: "✅ Finita", CopilotSessionStatus.FAILED: "❌ Fallita", CopilotSessionStatus.CANCELLED: "⏹️ Annullata"}
        files = f": {len(changed)} file modificati nel repository." if changed else ": nessun file modificato."
        self._message(session, CopilotMessageRole.EVENT, summary[status] + files)
        self._set_task_status(session, TaskStatus.DONE if status == CopilotSessionStatus.DONE else TaskStatus.TODO)
        return session

    # --------------------------------------------------------------- helpers
    def _record(self, session: CopilotSession, turn: CopilotTurn) -> CopilotSession:
        """Copilot's answer (or the error) as messages, and the requests used."""
        if turn.message:
            self._message(session, CopilotMessageRole.COPILOT, turn.message)
        if turn.error and not turn.cancelled:
            self._message(session, CopilotMessageRole.EVENT, f"❌ {turn.error}")
        return self._update(session, premium_requests=max(session.premium_requests, turn.premium_requests),
                            error=turn.error if not turn.cancelled else None)

    def _record_usage(self, session: CopilotSession, turn: CopilotTurn, phase: CopilotPhase, started: float) -> None:
        """The turn's row for observability. Copilot reports the session's
        totals: the turn used what they grew since the turns already recorded
        (a turn killed before writing them is caught up by the next one).
        Best effort: a failure here never stops the session."""
        try:
            previous = sum((recorded.usage for recorded in self._copilot.list_session_turns(session.id)), CopilotUsage())
            self._copilot.add_turn(CopilotTurnRecord(
                session_id=session.id,
                project_name=session.project_name,
                task_note=session.task_note,
                phase=phase,
                model=turn.model or session.model or self._client.model,
                ok=turn.error is None,
                cancelled=turn.cancelled,
                error=turn.error,
                duration_ms=int((time.monotonic() - started) * 1000),
                usage=turn.usage.since(previous) if turn.usage else CopilotUsage(),
            ))
        except Exception:  # noqa: BLE001 - observability must not break the session
            log_exception(LogPrefix.COPILOT_SERVICE, "Uso del turno non registrato (sessione %s)", session.id)

    def _task_folder(self, session: CopilotSession) -> list[Path]:
        """The task and its references as files, rebuilt now (they may have
        changed since the last turn); none when the task was deleted meanwhile."""
        try:
            return [self._data.copilot_folder(session.project_name, session.task_note, session.copilot_session_id)]
        except AppError:
            log_exception(LogPrefix.COPILOT_SERVICE, "Cartella del task %s non preparata", session.task_note)
            return []

    def _cancel_check(self, session_id: int) -> Callable[[], bool]:
        """Polled by the client while Copilot runs: reads the DB every few seconds."""
        last, requested = 0.0, False

        def should_cancel() -> bool:
            nonlocal last, requested
            if not requested and time.monotonic() - last >= _CANCEL_CHECK_SECONDS:
                last = time.monotonic()
                current = self._copilot.get_session(session_id)
                requested = current is None or current.cancel_requested
            return requested

        return should_cancel

    def _changed_files(self, session: CopilotSession) -> list[str]:
        """``git status`` of the session's repository: the changed files, untracked ones too."""
        return [change.path for change in self._git.status(session.project_name, session.repository).changes]

    def _set_task_status(self, session: CopilotSession, status: TaskStatus) -> None:
        """Best effort: the task may have been deleted or edited by hand meanwhile."""
        try:
            task = self._data.agent_task(session.project_name, session.task_note)
            if task.status != status:
                self._data.save_agent_task(session.project_name, session.task_note, task.model_copy(update={"status": status}))
        except AppError:
            log_exception(LogPrefix.COPILOT_SERVICE, "Stato del task %s non aggiornato", session.task_note)

    def _message(self, session: CopilotSession, role: CopilotMessageRole, content: str) -> None:
        self._copilot.add_message(CopilotMessage(session_id=session.id, role=role, content=content))

    def _update(self, session: CopilotSession, **changes) -> CopilotSession:
        """Writes only ``changes``: the API and the worker write the same
        session at the same time (e.g. a cancel while the execution starts)."""
        return self._copilot.update_session(session.id, **changes, updated_at=_now())
