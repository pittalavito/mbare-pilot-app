"""Agent tasks delegated to GitHub Copilot CLI (models/domain/copilot.py).

A session lives in two phases:

1. **Planning**: the first turn gives Copilot the task and asks it to read the
   code, ask its questions and propose a plan; then the user and Copilot chat.
   Plan mode: nothing changes. The API only saves the user's message and
   queues the turn (``planning_turn``): the worker runs Copilot and saves its
   answer, the page follows it by polling.
2. **Execution** (in the worker, after ``approve``): the same Copilot session
   resumes in autopilot and changes the files, minus the denied tools (no
   commits). HEAD is read before and after: if it moved, the session says so
   (nothing is undone: that is the user's call).

The prompts and the denied tools come from the coding-agent definition in the
data folder (domain/project/coding_agent.py), read at every use.

A session works on the repositories chosen when delegating (all of the
project's by default): with one Copilot starts in it, with more in the project
folder, told which ones. One execution at a time per repository: an execution
locks only its repositories, so sessions on different repositories of the same
project run in parallel. HEAD and ``git status`` are read in every repository
of the project, though: files changed outside the chosen ones are reported.
After an execution the chat can go on and a new ok starts a new one. Planning
turns do not wait for the repositories: plan mode only reads, so a turn can run
while another session executes on them (it may see files half changed). The
task's status follows: in progress while it runs, done when it succeeds, back
to todo otherwise."""
import time
from collections.abc import Callable, Sequence
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
    CopilotPlanningTurn,
    CopilotSession,
    CopilotSessionStatus,
    CopilotTurn,
    CopilotTurnRecord,
    CopilotUsage,
)
from models.domain.note import TaskStatus
from service.git_service import GitService
from service.project_data_service import ProjectDataService
from service.store_service import StoreService

_CANCEL_CHECK_SECONDS = 2.0


def _short(commit: str) -> str:
    return commit[:8] or "nessun commit"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _in_repo(repository: str, path: str) -> str:
    """A repository's file as ``<repository>/<path>``; just ``<path>`` for the project folder as repository."""
    return f"{repository}/{path}" if repository else path


def _label(repository: str) -> str:
    return repository or "(cartella del progetto)"


def _busy(session: CopilotSession) -> bool:
    """The worker has it, or will: an execution or a planning turn queued or running."""
    return session.planning_turn is not None or session.status in (CopilotSessionStatus.QUEUED, CopilotSessionStatus.RUNNING)


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

    @classmethod
    def from_config(cls, store_service: StoreService, git_service: GitService, project_data_service: ProjectDataService) -> "CopilotService":
        """The CLI, model, token and timeouts from the Config (COPILOT_*).
        ``git_service`` lists and checks the repositories and reads HEAD and
        ``git status`` around an execution (moved HEAD, changed files)."""
        config = Config.get()
        token = config.copilot_github_token.get_secret_value() if config.copilot_github_token else None
        return cls(
            store_service=store_service,
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
        used = {item.model: item for item in self._store.copilot_usage_by_model()}
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
        return self._store.list_copilot_sessions(project_name)

    def session(self, session_id: int) -> CopilotSession:
        session = self._store.get_copilot_session(session_id)
        if session is None:
            raise NotFoundError(f"Sessione Copilot non trovata: {session_id}")
        return session

    def messages(self, session_id: int) -> list[CopilotMessage]:
        return self._store.list_copilot_messages(self.session(session_id).id)

    # ----------------------------------------------------------------- usage
    def session_turns(self, session_id: int) -> list[CopilotTurnRecord]:
        """What each turn of the session used, oldest first."""
        return self._store.list_copilot_session_turns(self.session(session_id).id)

    def recent_turns(self, limit: int = 100, project_name: str | None = None) -> list[CopilotTurnRecord]:
        """Every session's turns, newest first (also of deleted sessions)."""
        return self._store.list_copilot_turns(limit, project_name)

    def usage_by_model(self, days: int | None = None, project_name: str | None = None) -> list[CopilotModelUsage]:
        """Totals per model over the last ``days`` (None = ever), the most AI credits first."""
        since = _now() - timedelta(days=days) if days else None
        return self._store.copilot_usage_by_model(since, project_name)

    # -------------------------------------------------------------- planning
    @observed(LogPrefix.COPILOT_SERVICE)
    def start(self, project_name: str, task_note: str, repositories: str | Sequence[str] = (), prompt: str = "", model: str = "") -> CopilotSession:
        """A new session on an agent task, with its first planning turn queued
        for the worker: returns at once, Copilot's questions (or the error)
        arrive later. ``repositories``: the project's repositories Copilot works
        on (a folder or a list of them; empty = all); ``prompt``: one of the
        definition's prompts (``""`` = ``plan_prompt``); ``model``: one of its
        models (``""`` = the default), for every turn. What can be checked now
        (CLI, definition, task, repositories) raises here."""
        if not self._client.available:
            raise UpstreamError(NOT_FOUND)
        settings = self.coding_agent(project_name)
        model = coding_agent.check_model(settings, model)
        task = self._data.agent_task(project_name, task_note)  # exists and is an agent task
        chosen = self._chosen_repositories(project_name, repositories)
        first_turn = coding_agent.plan_prompt(settings, self._data.read_note(project_name, task_note), prompt.strip())
        if len(chosen) > 1:
            first_turn += (f"\n\nLavori sui repository {', '.join(chosen)}: sono cartelle dentro quella del progetto, "
                           "da cui parti. Gli altri repository del progetto non vanno modificati.")
        session_id = str(uuid4())
        if task.references and (note := coding_agent.references_note(settings, self._data.copilot_folder(project_name, task_note, session_id))):
            first_turn += f"\n\n{note}"
        session = self._store.save_copilot_session(CopilotSession(
            project_name=project_name,
            task_note=task_note,
            repository=chosen[0] if len(chosen) == 1 else "",
            repositories=chosen,
            copilot_session_id=session_id,
            prompt=prompt.strip(),
            model=model,
        ))
        return self._queue_plan_turn(session, first_turn)

    @observed(LogPrefix.COPILOT_SERVICE)
    def send(self, session_id: int, text: str) -> CopilotSession:
        """A message of the planning chat, queued for the worker: returns at
        once, Copilot's answer arrives later. After an execution the chat goes
        on: the session is back to planning."""
        session = self.session(session_id)
        if session.status in (CopilotSessionStatus.QUEUED, CopilotSessionStatus.RUNNING):
            raise ConflictError("Copilot sta eseguendo il task: aspetta che finisca o annulla.")
        if session.planning_turn is not None:
            raise ConflictError("Copilot sta ancora rispondendo al messaggio precedente: aspetta la sua risposta.")
        if not text.strip():
            raise ValidationError("Il messaggio è vuoto.")
        self._workdir(session)
        return self._queue_plan_turn(session, text.strip())

    def _queue_plan_turn(self, session: CopilotSession, prompt: str) -> CopilotSession:
        """The user's message is the turn's prompt: the worker reads it back (the last ``user`` message)."""
        self._message(session, CopilotMessageRole.USER, prompt)
        return self._update(session, status=CopilotSessionStatus.PLANNING, planning_turn=CopilotPlanningTurn.QUEUED,
                            cancel_requested=False, error=None)

    @observed(LogPrefix.COPILOT_SERVICE)
    def approve(self, session_id: int) -> CopilotSession:
        """The user's ok: the execution goes in the worker's queue. Files
        already changed in the chosen repositories are listed, as a warning."""
        session = self.session(session_id)
        if session.status != CopilotSessionStatus.PLANNING:
            raise ConflictError("Si può dare l'ok solo durante la preparazione.")
        if session.planning_turn is not None:
            raise ConflictError("Copilot sta ancora rispondendo: aspetta la sua risposta prima di dare l'ok.")
        if not any(message.role == CopilotMessageRole.COPILOT for message in self._store.list_copilot_messages(session.id)):
            raise ConflictError("Copilot non ha ancora risposto: aspetta la sua risposta prima di dare l'ok.")
        changed = self._changed_files(session)
        if changed:
            listed = "\n".join(f"- {path}" for path in changed[:20]) + ("\n- …" if len(changed) > 20 else "")
            self._message(session, CopilotMessageRole.EVENT,
                          f"⚠️ Nei repository scelti ci sono già {len(changed)} file modificati: le modifiche di Copilot si aggiungeranno a queste.\n{listed}")
        self._message(session, CopilotMessageRole.EVENT,
                      "In coda: parte appena i suoi repository sono liberi (un'esecuzione alla volta per repository).")
        return self._update(session, status=CopilotSessionStatus.QUEUED, cancel_requested=False, error=None)

    @observed(LogPrefix.COPILOT_SERVICE)
    def cancel(self, session_id: int) -> CopilotSession:
        """A queued execution never starts; a running one is stopped by the
        worker. The same for a planning turn: the chat stays open."""
        session = self.session(session_id)
        if session.planning_turn == CopilotPlanningTurn.QUEUED:
            self._message(session, CopilotMessageRole.EVENT, "Messaggio annullato prima che Copilot lo leggesse.")
            return self._update(session, planning_turn=None)
        if session.planning_turn == CopilotPlanningTurn.RUNNING:
            self._message(session, CopilotMessageRole.EVENT, "Annullamento richiesto: il worker ferma Copilot.")
            return self._update(session, cancel_requested=True)
        if session.status == CopilotSessionStatus.QUEUED:
            self._message(session, CopilotMessageRole.EVENT, "Annullata prima di partire.")
            return self._update(session, status=CopilotSessionStatus.CANCELLED, finished_at=_now())
        if session.status == CopilotSessionStatus.RUNNING:
            self._message(session, CopilotMessageRole.EVENT, "Annullamento richiesto: il worker ferma Copilot.")
            return self._update(session, cancel_requested=True)
        raise ConflictError("Non c'è un'esecuzione o una risposta di Copilot da annullare.")

    @observed(LogPrefix.COPILOT_SERVICE)
    def delete(self, session_id: int) -> None:
        """With its messages; the files Copilot changed stay. Copilot's own session stays in its folder."""
        session = self.session(session_id)
        if _busy(session):
            raise ConflictError("La sessione è in coda o in esecuzione: annullala prima.")
        self._store.delete_copilot_session(session.id)
        self._data.delete_copilot_folder(session.project_name, session.copilot_session_id)

    @observed(LogPrefix.COPILOT_SERVICE)
    def delete_task_sessions(self, project_name: str, task_note: str) -> int:
        """Every session of an agent task (e.g. before deleting the task), with
        their messages; none if one of them is queued or running. The usage of
        their turns stays in Observability. Returns how many were deleted."""
        name = note_file_name(task_note)
        sessions = [session for session in self._store.list_copilot_sessions(project_name) if note_file_name(session.task_note) == name]
        if any(_busy(session) for session in sessions):
            raise ConflictError("Una sessione di questo task è in coda o in esecuzione: annullala prima.")
        for session in sessions:
            self._store.delete_copilot_session(session.id)
            self._data.delete_copilot_folder(project_name, session.copilot_session_id)
        return len(sessions)

    # ---------------------------------------------------------------- worker
    def plan_next(self, on_claim: Callable[[CopilotSession], None] | None = None, worker_id: str | None = None) -> CopilotSession | None:
        """Answer the planning turn that has waited longest (plan mode, read
        only: also while the repository has an execution running); None when
        there is none. Copilot's answer (or the error) becomes the session's
        messages, the turn's usage a row for Observability."""
        session = self.claim_planning_turn(worker_id)
        if session is None:
            return None
        if on_claim:
            on_claim(session)
        return self.answer(session)

    def claim_planning_turn(self, worker_id: str | None = None) -> CopilotSession | None:
        """The planning turn that has waited longest, now ``running`` and ``worker_id``'s; None when there is none."""
        return self._store.claim_next_copilot_planning_turn(worker_id)

    def answer(self, session: CopilotSession) -> CopilotSession:
        """Run a claimed planning turn (``claim_planning_turn``) and save Copilot's answer."""
        try:
            folder = self._workdir(session)
        except AppError as exc:
            self._message(session, CopilotMessageRole.EVENT, f"❌ {exc}")
            return self._update(session, planning_turn=None, cancel_requested=False, error=str(exc))
        prompt = next((message.content for message in reversed(self._store.list_copilot_messages(session.id))
                       if message.role == CopilotMessageRole.USER), "")
        started = time.monotonic()
        turn = self._client.turn(folder, session.copilot_session_id, prompt, CopilotMode.PLAN, self._planning_timeout,
                                 should_cancel=self._cancel_check(session.id), model=session.model, extra_dirs=self._task_folder(session))
        self._record_usage(session, turn, CopilotPhase.PLAN, started)
        session = self._record(session, turn)
        if turn.cancelled:
            self._message(session, CopilotMessageRole.EVENT, "⏹️ Risposta annullata: puoi scrivere un altro messaggio.")
        return self._update(session, planning_turn=None, cancel_requested=False)

    def run_next(self, on_claim: Callable[[CopilotSession], None] | None = None, worker_id: str | None = None) -> CopilotSession | None:
        """Execute the next queued session whose repositories are all free; None when there is none."""
        session = self.claim_execution(worker_id)
        if session is None:
            return None
        if on_claim:
            on_claim(session)
        return self.execute(session)

    def claim_execution(self, worker_id: str | None = None) -> CopilotSession | None:
        """The oldest queued execution whose repositories are all free, now ``running``
        and ``worker_id``'s; None when there is none."""
        return self._store.claim_next_copilot_session(worker_id)

    def execute(self, session: CopilotSession) -> CopilotSession:
        """Run a claimed execution (``claim_execution``) to its end: done, failed or cancelled."""
        try:
            settings = self.coding_agent(session.project_name)
            folder = self._workdir(session)
            heads_before, changes_before = self._snapshot(session.project_name)
        except AppError as exc:
            self._message(session, CopilotMessageRole.EVENT, f"❌ Non partita: {exc}")
            return self._update(session, status=CopilotSessionStatus.FAILED, error=str(exc), finished_at=_now())
        session = self._update(session, heads_before=heads_before, heads_after=None, head_before=None, head_after=None,
                               changed_files=[], outside_files=[], error=None)
        self._message(session, CopilotMessageRole.EVENT, "▶️ Esecuzione partita: Copilot modifica i file, senza commit.")
        self._set_task_status(session, TaskStatus.IN_PROGRESS)
        self._message(session, CopilotMessageRole.USER, settings.execute_prompt)
        started = time.monotonic()
        turn = self._client.turn(folder, session.copilot_session_id, settings.execute_prompt, CopilotMode.EXECUTE,
                                 self._execution_timeout, settings.denied_tools, self._cancel_check(session.id), model=session.model,
                                 extra_dirs=self._task_folder(session))
        self._record_usage(session, turn, CopilotPhase.EXECUTE, started)
        session = self._record(session, turn)
        return self._finish(session, turn, changes_before)

    def fail_orphaned(self, alive_workers: set[str]) -> int:
        """The executions and the planning turns left ``running`` by a worker
        that is not among ``alive_workers`` (it stopped beating: it died), or
        unknown (claimed before ``claimed_by``). The workers check it now and
        then. An execution fails; a planning turn ends with the error and the
        chat stays open (the user sends again). Returns how many."""
        orphaned = lambda session: session.claimed_by not in alive_workers  # noqa: E731
        sessions = [session for session in self._store.list_copilot_sessions_by_status(CopilotSessionStatus.RUNNING) if orphaned(session)]
        for session in sessions:
            self._message(session, CopilotMessageRole.EVENT, "❌ Interrotta: il worker si è fermato durante l'esecuzione.")
            self._update(session, status=CopilotSessionStatus.FAILED, error="Worker interrotto.", finished_at=_now())
            self._set_task_status(session, TaskStatus.TODO)
        turns = [session for session in self._store.list_copilot_sessions_by_planning_turn(CopilotPlanningTurn.RUNNING) if orphaned(session)]
        for session in turns:
            self._message(session, CopilotMessageRole.EVENT,
                          "❌ Interrotta: il worker si è fermato mentre Copilot rispondeva. Manda di nuovo il messaggio.")
            self._update(session, planning_turn=None, cancel_requested=False, error="Worker interrotto.")
        return len(sessions) + len(turns)

    def _finish(self, session: CopilotSession, turn: CopilotTurn, changes_before: dict[str, list[str]]) -> CopilotSession:
        heads_after: dict[str, str] = {}
        changes: dict[str, list[str]] = {}
        try:
            heads_after, changes = self._snapshot(session.project_name)
        except AppError:
            log_exception(LogPrefix.COPILOT_SERVICE, "Stato git non letto a fine esecuzione")
        chosen = set(session.repos)
        changed = sorted(path for repo in chosen for path in changes.get(repo, []))
        dirty_before = {path for paths in changes_before.values() for path in paths}
        outside = sorted(path for repo, paths in changes.items() if repo not in chosen for path in paths if path not in dirty_before)
        status = (
            CopilotSessionStatus.CANCELLED if turn.cancelled
            else CopilotSessionStatus.FAILED if turn.error else CopilotSessionStatus.DONE
        )
        session = self._update(session, status=status, heads_after=heads_after or None, changed_files=changed, outside_files=outside,
                               cancel_requested=False, finished_at=_now())
        others = self._others_running(session)
        if moved := session.moved_repositories:
            heads = "; ".join(f"{_label(repo)}: {_short((session.heads_before or {}).get(repo, ''))} → {_short(heads_after.get(repo, ''))}"
                              for repo in moved)
            self._message(session, CopilotMessageRole.EVENT,
                          f"⚠️ L'HEAD è cambiato durante l'esecuzione ({heads}): un commit o un'altra operazione git non autorizzata"
                          f"{others}. Controlla prima di continuare: non ho annullato niente.")
        if outside:
            listed = "\n".join(f"- {path}" for path in outside[:20]) + ("\n- …" if len(outside) > 20 else "")
            self._message(session, CopilotMessageRole.EVENT,
                          f"⚠️ Cambiati {len(outside)} file in repository non scelti{others}:\n{listed}")
        summary = {CopilotSessionStatus.DONE: "✅ Finita", CopilotSessionStatus.FAILED: "❌ Fallita", CopilotSessionStatus.CANCELLED: "⏹️ Annullata"}
        files = f": {len(changed)} file modificati nei repository scelti." if changed else ": nessun file modificato."
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
            previous = sum((recorded.usage for recorded in self._store.list_copilot_session_turns(session.id)), CopilotUsage())
            self._store.add_copilot_turn(CopilotTurnRecord(
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
                current = self._store.get_copilot_session(session_id)
                requested = current is None or current.cancel_requested
            return requested

        return should_cancel

    def _changed_files(self, session: CopilotSession) -> list[str]:
        """``git status`` of the chosen repositories: the changed files, untracked ones too (``<repository>/<path>``)."""
        return [_in_repo(repo, change.path) for repo in session.repos for change in self._git.status(session.project_name, repo).changes]

    def _chosen_repositories(self, project_name: str, repositories: str | Sequence[str]) -> list[str]:
        """The repositories asked for, checked and sorted; none = every repository of the project."""
        asked = [repositories] if isinstance(repositories, str) else list(repositories)
        available = [repo.path for repo in self._git.repositories(project_name)]
        if not asked:
            if not available:
                raise ValidationError("Nessun repository git nella cartella del progetto.")
            return available
        chosen = sorted({repo.strip().strip("/\\").replace("\\", "/") for repo in asked})
        for repo in chosen:
            self._git.repository_folder(project_name, repo)  # inside the project and a repository
            if repo not in available:
                raise ValidationError(f"{_label(repo)} non è un repository del progetto. Disponibili: "
                                      f"{', '.join(_label(path) for path in available) or 'nessuno'}.")
        return chosen

    def _workdir(self, session: CopilotSession) -> Path:
        """Where Copilot starts: the only chosen repository, or the project folder
        with more. Each chosen repository is checked: it may have been moved meanwhile."""
        folders = [self._git.repository_folder(session.project_name, repo) for repo in session.repos]
        return folders[0] if len(folders) == 1 else self._git.root_folder(session.project_name)

    def _snapshot(self, project_name: str) -> tuple[dict[str, str], dict[str, list[str]]]:
        """HEAD and changed files (``<repository>/<path>``) of every repository of
        the project. A repository that cannot be read is skipped (logged)."""
        heads: dict[str, str] = {}
        changes: dict[str, list[str]] = {}
        for repo in self._git.repositories(project_name):
            try:
                heads[repo.path] = self._git.head(project_name, repo.path)
                changes[repo.path] = [_in_repo(repo.path, change.path) for change in self._git.status(project_name, repo.path).changes]
            except AppError:
                log_exception(LogPrefix.COPILOT_SERVICE, "Stato git di %s non letto", repo.path)
        return heads, changes

    def _others_running(self, session: CopilotSession) -> str:
        """`` (forse di un'altra esecuzione …)`` when other executions run in the project: they may have done it."""
        others = [other for other in self._store.list_copilot_sessions_by_status(CopilotSessionStatus.RUNNING)
                  if other.project_name == session.project_name and other.id != session.id]
        return " (forse di un'altra esecuzione in corso nel progetto)" if others else ""

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
