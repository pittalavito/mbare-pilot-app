"""Agent tasks delegated to GitHub Copilot CLI (models/domain/copilot.py).

A session lives in two phases:

1. **Planning** (in the API, while the user waits): the first turn gives
   Copilot the task and asks it to read the code, ask its questions and
   propose a plan; then the user and Copilot chat. Plan mode: nothing changes.
2. **Execution** (in the worker, after ``approve``): the same Copilot session
   resumes in autopilot and changes the files, never commits
   (``EXECUTION_DENIED``). HEAD is read before and after: if it moved, the
   session says so (nothing is undone: that is the user's call).

One execution at a time per repository (the queue waits); after an execution
the chat can go on and a new ok starts a new one. The task's status follows:
in progress while it runs, done when it succeeds, back to todo otherwise."""
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.error import AppError, ConflictError, NotFoundError, UpstreamError, ValidationError
from core.observability import LogPrefix, log_exception, observed
from domain.client.copilot.client import CopilotClient, CopilotMode
from models.domain.copilot import CopilotMessage, CopilotMessageRole, CopilotSession, CopilotSessionStatus, CopilotTurn
from models.domain.note import TaskStatus
from service.git_service import GitService
from service.project_data_service import ProjectDataService
from service.store_service import StoreService

# todof: scriviao meglio sta parte di
FIRST_PROMPT = """Ti affido il task qui sotto, sul repository in cui ti trovi. Prima di cambiare qualcosa:
1. leggi il codice che ti serve;
2. fammi le domande necessarie per chiarire il task, poche e precise;
3. quando non hai più domande, proponi un piano breve e aspetta il mio ok.
Parliamo attraverso un'app, a turni: ogni mio messaggio ti arriva come un nuovo turno, quindi fai pure le tue domande e aspetta la risposta. Adesso sei in modalità piano e non puoi modificare niente: è giusto così. Il via lo do io con il pulsante «Ok, parti» dell'app, che ti riattiva per eseguire il piano; non chiedermi di uscire dalla modalità piano né di premere tasti. Anche dopo l'ok non farai commit, push né altre operazioni git che cambiano la storia, l'indice o i branch: il commit lo faccio io.

{task}"""

EXECUTE_PROMPT = (
    "Ok, procedi con il piano concordato. Non fare commit, push né altre operazioni git che cambiano la storia, "
    "l'indice o i branch. Alla fine riassumi cosa hai cambiato (file e motivo) e se i criteri di accettazione sono soddisfatti."
)

_CANCEL_CHECK_SECONDS = 2.0


def _short(commit: str) -> str:
    return commit[:8] or "nessun commit"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CopilotService:

    def __init__(
        self,
        store_service: StoreService,
        git_service: GitService,
        project_data_service: ProjectDataService,
        client: CopilotClient,
        planning_timeout_seconds: float,
        execution_timeout_seconds: float,
    ):
        self._store = store_service
        self._git = git_service
        self._data = project_data_service
        self._client = client
        self._planning_timeout = planning_timeout_seconds
        self._execution_timeout = execution_timeout_seconds

    # ------------------------------------------------------------------ read
    def version(self) -> str | None:
        """The installed Copilot CLI, None when missing."""
        return self._client.version()

    def sessions(self, project_name: str) -> list[CopilotSession]:
        """A project's sessions, newest first."""
        return self._store.list_copilot_sessions(project_name)

    def session(self, session_id: int) -> CopilotSession:
        session = self._store.get_copilot_session(session_id)
        if session is None:
            raise NotFoundError(f"Sessione Copilot non trovata: {session_id}")
        return session

    def messages(self, session_id: int) -> list[CopilotMessage]:
        return self._store.list_copilot_messages(self.session(session_id).id)

    # -------------------------------------------------------------- planning
    @observed(LogPrefix.COPILOT_SERVICE)
    def start(self, project_name: str, task_note: str, repository: str = "") -> CopilotSession:
        """A new session on an agent task: the first planning turn runs now,
        so the session comes back with Copilot's questions (or the error)."""
        if not self._client.available:
            raise UpstreamError("Copilot CLI non trovato: installalo (npm install -g @github/copilot) e fai il login.")
        self._data.agent_task(project_name, task_note)  # exists and is an agent task
        folder = self._git.repository_folder(project_name, repository)
        task = self._data.read_note(project_name, task_note)
        session = self._store.save_copilot_session(CopilotSession(
            project_name=project_name, task_note=task_note, repository=repository.strip().strip("/\\"),
            copilot_session_id=str(uuid4()),
        ))
        return self._plan_turn(session, folder, FIRST_PROMPT.format(task=task.strip()))

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
        turn = self._client.turn(folder, session.copilot_session_id, prompt, CopilotMode.PLAN, self._planning_timeout)
        return self._record(session, turn)

    @observed(LogPrefix.COPILOT_SERVICE)
    def approve(self, session_id: int) -> CopilotSession:
        """The user's ok: the execution goes in the worker's queue. Files
        already changed in the repository are listed, as a warning."""
        session = self.session(session_id)
        if session.status != CopilotSessionStatus.PLANNING:
            raise ConflictError("Si può dare l'ok solo durante la preparazione.")
        if not any(message.role == CopilotMessageRole.COPILOT for message in self._store.list_copilot_messages(session.id)):
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
        self._store.delete_copilot_session(session.id)

    # ---------------------------------------------------------------- worker
    def run_next(self, on_claim: Callable[[CopilotSession], None] | None = None) -> CopilotSession | None:
        """Execute the next queued session whose repository is free; None when there is none."""
        session = self._store.claim_next_copilot_session()
        if session is None:
            return None
        if on_claim:
            on_claim(session)
        try:
            folder = self._git.repository_folder(session.project_name, session.repository)
            head_before = self._git.head(session.project_name, session.repository)
        except AppError as exc:
            self._message(session, CopilotMessageRole.EVENT, f"❌ Non partita: {exc}")
            return self._update(session, status=CopilotSessionStatus.FAILED, error=str(exc), finished_at=_now())
        session = self._update(session, head_before=head_before, head_after=None, changed_files=[], error=None)
        self._message(session, CopilotMessageRole.EVENT, "▶️ Esecuzione partita: Copilot modifica i file, senza commit.")
        self._set_task_status(session, TaskStatus.IN_PROGRESS)
        self._message(session, CopilotMessageRole.USER, EXECUTE_PROMPT)
        turn = self._client.turn(folder, session.copilot_session_id, EXECUTE_PROMPT, CopilotMode.EXECUTE,
                                 self._execution_timeout, self._cancel_check(session.id))
        session = self._record(session, turn)
        return self._finish(session, turn)

    def fail_interrupted(self) -> int:
        """At the worker's start: the executions left ``running`` by a worker that died."""
        sessions = self._store.list_copilot_sessions_by_status(CopilotSessionStatus.RUNNING)
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

    def _cancel_check(self, session_id: int) -> Callable[[], bool]:
        """Polled by the client while Copilot runs: reads the DB every few seconds."""
        last, requested = 0.0, False

        def should_cancel() -> bool:
            nonlocal last, requested
            if not requested and time.monotonic() - last >= _CANCEL_CHECK_SECONDS:
                last = time.monotonic()
                current = self._store.get_copilot_session(session_id)
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
        self._store.add_copilot_message(CopilotMessage(session_id=session.id, role=role, content=content))

    def _update(self, session: CopilotSession, **changes) -> CopilotSession:
        """Writes only ``changes``: the API and the worker write the same
        session at the same time (e.g. a cancel while the execution starts)."""
        return self._store.update_copilot_session(session.id, **changes, updated_at=_now())
