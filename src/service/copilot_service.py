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

The task reaches Copilot through the app's **MCP server**
(controller/mcp_server.py): every session has its own token, valid only for
its task; each turn gives Copilot the server and the token (``McpAccess``),
after checking that the server answers (no answer = the turn does not start).
In the repository there is only a minimal ``mbare-pilot/<task note>/task.md``
(domain/project/task_folder.py): title, type and where the rest is; the
prompt says where it is (``{task_folder}``). The app keeps that folder out of
its lists of changed files.

The MCP tools are methods here: ``mcp_task``, ``mcp_links``, ``mcp_link``,
``ask_user`` (during an execution: the question goes in the chat and the tool
waits for the user's answer, ``answer``, up to a timeout) and ``finish``
(Copilot's summary; a development becomes «to verify»).

One execution at a time per repository (the queue waits); after an execution
the chat can go on and a new ok starts a new one. The task's status follows:
in progress while it runs, to verify when it succeeds (the user checks the
changes and confirms, or sends the task back to Copilot with a message: a new
execution of the same session), back to todo otherwise.

Only a development task is executed. The other types (analysis, Confluence,
Jira: ``TaskType.plan_only``) stay in planning: Copilot reads and answers, and
the user saves its last answer as a note linked to the task, which becomes done."""
import secrets
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from config import Config
from core.error import AppError, ConflictError, NotFoundError, UpstreamError, ValidationError
from core.observability import LogPrefix, log_exception, observed
from domain.client.copilot.client import NOT_FOUND, CopilotClient, CopilotMode, McpAccess
from domain.project import coding_agent, task_folder
from domain.project.data_paths import note_file_name, slug
from domain.project.note_templates import NOTE_PREFIXES_BY_TYPE, STATUS_LABELS, TYPE_LABELS
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
from models.domain.note import AgentTask, TaskLink, TaskStatus, TaskType
from service.git_service import GitService
from service.project_data_service import ProjectDataService
from service.store.copilot_store import CopilotStore
from service.store.definition_store import DefinitionStore

_CANCEL_CHECK_SECONDS = 2.0


def _short(commit: str) -> str:
    return commit[:8] or "nessun commit"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def output_note_name(task_note: str, task_type: TaskType) -> str:
    """Where a plan-only task's answer is saved: ``agent-task-login.md`` →
    ``analisi-login.md`` (an analysis) or ``bozza-login.md`` (a draft)."""
    name = note_file_name(task_note).removesuffix(".md")
    name = name[len("agent-task-"):] if name.lower().startswith("agent-task-") else name
    return note_file_name(NOTE_PREFIXES_BY_TYPE[task_type] + slug(name, "task"))


def not_refined_warning(status: TaskStatus) -> str | None:
    """For a task delegated before it is ready (created, refinement); None when it is."""
    if status.is_refined:
        return None
    return (f"⚠️ Il task è «{STATUS_LABELS[status]}», non ancora «{STATUS_LABELS[TaskStatus.TODO]}»: "
            "Copilot lo legge com'è, magari ancora da rifinire.")


class CopilotService:

    def __init__(
        self,
        definitions: DefinitionStore,
        copilot: CopilotStore,
        git_service: GitService,
        project_data_service: ProjectDataService,
        client: CopilotClient,
        planning_timeout_seconds: float,
        execution_timeout_seconds: float,
        mcp_url: str | None = None,
        mcp_check: Callable[[str], str | None] | None = None,
        ask_user_timeout_seconds: float = 600.0,
        poll_seconds: float = 1.0,
    ):
        """``mcp_url``: the app's MCP server as Copilot reaches it (None = the
        turns go without it, e.g. in tests); ``mcp_check(url)``: why it does
        not answer, None when it does (None = not checked);
        ``ask_user_timeout_seconds``: how long ``ask_user`` waits for the
        answer, reading the DB every ``poll_seconds``."""
        self._mcp_url = mcp_url
        self._mcp_check = mcp_check
        self._ask_timeout = ask_user_timeout_seconds
        self._poll = poll_seconds
        self._definitions = definitions
        self._copilot = copilot
        self._git = git_service
        self._data = project_data_service
        self._client = client
        self._planning_timeout = planning_timeout_seconds
        self._execution_timeout = execution_timeout_seconds

    @classmethod
    def from_config(cls, definitions: DefinitionStore, copilot: CopilotStore, git_service: GitService,
                    project_data_service: ProjectDataService) -> "CopilotService":
        """The CLI, model, token and timeouts from the Config (COPILOT_*).
        ``git_service`` resolves the repository folder and reads HEAD and
        ``git status`` around an execution (moved HEAD, changed files)."""
        config = Config.get()
        token = config.copilot_github_token.get_secret_value() if config.copilot_github_token else None
        return cls(
            definitions=definitions,
            copilot=copilot,
            git_service=git_service,
            project_data_service=project_data_service,
            client=CopilotClient(config.copilot_command, config.copilot_model, token),
            planning_timeout_seconds=config.copilot_planning_timeout_minutes * 60,
            execution_timeout_seconds=config.copilot_execution_timeout_minutes * 60,
            mcp_url=mcp_url(config.api_url),
            mcp_check=mcp_unreachable,
            ask_user_timeout_seconds=config.copilot_ask_user_timeout_minutes * 60,
        )

    # ------------------------------------------------------------------ read
    def version(self) -> str | None:
        """The installed Copilot CLI, None when missing."""
        return self._client.version()

    def coding_agent(self, project_name: str | None = None) -> CodingAgentSettings:
        """Prompts and denied tools: the global definition, with the project's
        fields over it. Raises ValidationError when missing or broken."""
        return coding_agent.load(self._definitions, project_name)

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
        ``prompt``: one of the definition's prompts (``""`` = the one of the
        task's type in ``type_prompts``, else ``plan_prompt``); ``model``: one
        of its models (``""`` = the default), for every turn. A task not
        refined yet (created, refinement) can be delegated: the chat says so."""
        if not self._client.available:
            raise UpstreamError(NOT_FOUND)
        settings = self.coding_agent(project_name)
        model = coding_agent.check_model(settings, model)
        task = self._data.agent_task(project_name, task_note)  # exists and is an agent task
        folder = self._git.repository_folder(project_name, repository)
        prompt = coding_agent.task_prompt(settings, task.type, prompt)
        first_turn = coding_agent.plan_prompt(settings, task_folder.relative_folder(task_note), prompt)
        self._require_mcp()
        task_folder.write(folder, task_note, task_folder.minimal_task(task_note, task.title, TYPE_LABELS[task.type]))  # errors stop here
        session = self._copilot.save_session(CopilotSession(
            project_name=project_name,
            task_note=task_note,
            repository=repository.strip().strip("/\\"),
            copilot_session_id=str(uuid4()),
            prompt=prompt,
            model=model,
            mcp_token=secrets.token_urlsafe(32),
        ))
        if (warning := not_refined_warning(task.status)):
            self._message(session, CopilotMessageRole.EVENT, warning)
        if task.type.plan_only:
            self._message(session, CopilotMessageRole.EVENT,
                          "Questo tipo di task non cambia il codice: Copilot resta in preparazione e risponde. "
                          "Quando la risposta va bene, «Salva come nota»: diventa una nota collegata al task, che passa a «fatto».")
            if task.status == TaskStatus.TODO:
                self._set_task_status(session, TaskStatus.IN_PROGRESS)
        return self._plan_turn(session, folder, first_turn, refresh=False)

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
        self._require_mcp()
        return self._plan_turn(session, folder, text.strip())

    def _plan_turn(self, session: CopilotSession, folder: Path, prompt: str, refresh: bool = True) -> CopilotSession:
        """``refresh``: rebuild the task's folder first (``start`` just wrote it)."""
        if refresh:
            self._refresh_task_folder(session, folder)
        self._message(session, CopilotMessageRole.USER, prompt)
        session = self._update(session, status=CopilotSessionStatus.PLANNING, error=None)
        started = time.monotonic()
        turn = self._client.turn(folder, session.copilot_session_id, prompt, CopilotMode.PLAN, self._planning_timeout, model=session.model,
                                 mcp=self._access(session))
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
        self._refuse_plan_only(session)
        changed = self._changed_files(session)
        if changed:
            listed = "\n".join(f"- {path}" for path in changed[:20]) + ("\n- …" if len(changed) > 20 else "")
            self._message(session, CopilotMessageRole.EVENT,
                          f"⚠️ Nel repository ci sono già {len(changed)} file modificati: le modifiche di Copilot si aggiungeranno a queste.\n{listed}")
        self._message(session, CopilotMessageRole.EVENT, "In coda: parte appena il worker è libero (un'esecuzione alla volta per repository).")
        return self._update(session, status=CopilotSessionStatus.QUEUED, cancel_requested=False, error=None)

    @observed(LogPrefix.COPILOT_SERVICE)
    def send_back(self, session_id: int, text: str) -> CopilotSession:
        """The task is to verify and needs more work: ``text`` (what to fix)
        starts a new execution of the same Copilot session, which remembers the
        plan and its changes. It goes in the worker's queue like an ok."""
        session = self.session(session_id)
        if session.status in (CopilotSessionStatus.QUEUED, CopilotSessionStatus.RUNNING):
            raise ConflictError("Copilot sta già eseguendo il task: aspetta che finisca o annulla.")
        if not text.strip():
            raise ValidationError("Scrivi cosa deve sistemare Copilot.")
        task = self._data.agent_task(session.project_name, session.task_note)
        if task.status != TaskStatus.TO_VERIFY:
            raise ConflictError(f"Si rimanda a Copilot solo un task «{STATUS_LABELS[TaskStatus.TO_VERIFY]}»: "
                                f"questo è «{STATUS_LABELS[task.status]}».")
        self._refuse_plan_only(session)
        self._message(session, CopilotMessageRole.EVENT, "↩️ Rimandato a Copilot. In coda: parte appena il worker è libero.")
        return self._update(session, status=CopilotSessionStatus.QUEUED, next_prompt=text.strip(), cancel_requested=False, error=None)

    @observed(LogPrefix.COPILOT_SERVICE)
    def save_as_note(self, session_id: int) -> tuple[str, CopilotSession]:
        """A plan-only task (analysis, Confluence, Jira): Copilot's last answer
        becomes a note (``analisi-<task>.md`` or ``bozza-<task>.md``, rewritten
        when it exists), linked to the task, which becomes done. Returns the
        note's name and the session."""
        session = self.session(session_id)
        if session.status in (CopilotSessionStatus.QUEUED, CopilotSessionStatus.RUNNING):
            raise ConflictError("Copilot sta eseguendo il task: aspetta che finisca o annulla.")
        answer = next((message.content for message in reversed(self._copilot.list_messages(session.id))
                       if message.role == CopilotMessageRole.COPILOT and message.content.strip()), None)
        if answer is None:
            raise ConflictError("Copilot non ha ancora risposto: non c'è niente da salvare.")
        task = self._data.agent_task(session.project_name, session.task_note)
        if not task.type.plan_only:
            raise ConflictError("Un task di sviluppo non si salva come nota: Copilot cambia il codice, con «Ok, parti».")
        note = output_note_name(session.task_note, task.type)
        heading = "Analisi" if task.type == TaskType.ANALYSIS else "Bozza"
        self._data.save_note(session.project_name, note, f"# {heading}: {task.title}\n\n{answer.strip()}\n")
        references = task.references if note in task.references else [*task.references, note]
        self._data.save_agent_task(session.project_name, session.task_note,
                                   task.model_copy(update={"references": references, "status": TaskStatus.DONE}))
        self._message(session, CopilotMessageRole.EVENT, f"💾 Salvata come nota {note}, collegata al task: il task è «fatto».")
        return note, self.session(session.id)

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
        """With its messages; the files Copilot changed and the task's folder in
        the repository stay. Copilot's own session stays in its folder."""
        session = self.session(session_id)
        if session.status in (CopilotSessionStatus.QUEUED, CopilotSessionStatus.RUNNING):
            raise ConflictError("La sessione è in coda o in esecuzione: annullala prima.")
        self._copilot.delete_session(session.id)

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
        return len(sessions)

    # ------------------------------------------------------------------- mcp
    def mcp_session(self, token: str) -> CopilotSession:
        """The session of an MCP token; ValidationError for an unknown one (a
        deleted session's token is gone with it)."""
        session = self._copilot.get_session_by_token(token.strip())
        if session is None:
            raise ValidationError("Token MCP non valido: vale solo per la sua sessione Copilot.")
        return session

    def mcp_task(self, token: str) -> dict:
        """The session's task, every field, with the checklist of its type."""
        session = self.mcp_session(token)
        task = self._data.agent_task(session.project_name, session.task_note)
        settings, _ = self.coding_agent_or_error(session.project_name)
        return {
            "task": session.task_note, "title": task.title, "type": task.type.value, "status": task.status.value,
            "objective": task.objective, "context": task.context, "acceptance_criteria": [item.text for item in task.criteria],
            "constraints": task.constraints, "checklist": coding_agent.task_checklist(settings, task.type) if settings else [],
        }

    def mcp_links(self, token: str) -> list[TaskLink]:
        """What the session's task links (references, notes, files), by name."""
        session = self.mcp_session(token)
        return self._data.task_links(session.project_name, session.task_note)

    def mcp_link(self, token: str, name: str) -> str:
        """The content of one of them, as text."""
        session = self.mcp_session(token)
        return self._data.task_link_text(session.project_name, session.task_note, name)

    def ask_user(self, token: str, question: str) -> str:
        """During an execution: the question goes in the chat and this waits
        for the user's answer (``answer``), reading the DB every few seconds,
        up to the timeout or until the execution is cancelled. While planning
        Copilot asks in its answer instead."""
        session = self.mcp_session(token)
        if not question.strip():
            raise ValidationError("La domanda è vuota.")
        if session.status != CopilotSessionStatus.RUNNING:
            return "Non sei in esecuzione: scrivi la domanda nella tua risposta, ti rispondo nella chat."
        asked = self._copilot.add_message(CopilotMessage(session_id=session.id, role=CopilotMessageRole.QUESTION, content=question.strip()))
        deadline = time.monotonic() + self._ask_timeout
        while True:
            current = self._copilot.get_session(session.id)
            if current is None or current.cancel_requested:
                return "Esecuzione annullata: fermati."
            answer = next((message.content for message in self._copilot.list_messages(session.id)
                           if message.role == CopilotMessageRole.USER and (message.id or 0) > (asked.id or 0)), None)
            if answer is not None:
                return answer
            if time.monotonic() >= deadline:
                self._message(session, CopilotMessageRole.EVENT, "⏱️ Nessuna risposta in tempo: Copilot decide da solo.")
                return "Nessuna risposta: decidi tu e scrivilo nel riassunto di finish."
            time.sleep(self._poll)

    @observed(LogPrefix.COPILOT_SERVICE)
    def answer(self, session_id: int, text: str) -> CopilotSession:
        """The user's answer to Copilot's pending question (``ask_user``)
        during an execution. ConflictError when there is no question waiting."""
        session = self.session(session_id)
        if not text.strip():
            raise ValidationError("La risposta è vuota.")
        if session.status != CopilotSessionStatus.RUNNING or self.pending_question(session.id) is None:
            raise ConflictError("Copilot non ti ha fatto domande: non c'è niente a cui rispondere.")
        self._message(session, CopilotMessageRole.USER, text.strip())
        return self.session(session.id)

    def pending_question(self, session_id: int) -> CopilotMessage | None:
        """Copilot's last question when no user message came after it."""
        for message in reversed(self._copilot.list_messages(session_id)):
            if message.role == CopilotMessageRole.USER:
                return None
            if message.role == CopilotMessageRole.QUESTION:
                return message
        return None

    def finish(self, token: str, summary: str) -> str:
        """Copilot says it is done: the summary goes in the chat and, during
        the execution of a development, the task becomes «to verify» (the end
        of the turn does the same when Copilot does not call this)."""
        session = self.mcp_session(token)
        if session.status != CopilotSessionStatus.RUNNING:
            return "Non sei in esecuzione: rispondi nella chat."
        self._message(session, CopilotMessageRole.COPILOT, f"🏁 {summary.strip() or 'Fatto.'}")
        try:
            task = self._data.agent_task(session.project_name, session.task_note)
        except AppError:
            return "Ricevuto (il task non esiste più)."
        if not task.type.plan_only:
            self._set_task_status(session, TaskStatus.TO_VERIFY)
        return "Ricevuto: l'utente controlla il lavoro."

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
            self._require_mcp()
        except AppError as exc:
            self._message(session, CopilotMessageRole.EVENT, f"❌ Non partita: {exc}")
            return self._update(session, status=CopilotSessionStatus.FAILED, error=str(exc), finished_at=_now())
        prompt = session.next_prompt or settings.execute_prompt  # sent back to Copilot: the user's message
        session = self._update(session, head_before=head_before, head_after=None, changed_files=[], error=None, next_prompt="")
        self._message(session, CopilotMessageRole.EVENT, "▶️ Esecuzione partita: Copilot modifica i file, senza commit.")
        self._set_task_status(session, TaskStatus.IN_PROGRESS)  # before the folder: task.md says «in corso»
        self._refresh_task_folder(session, folder)
        self._message(session, CopilotMessageRole.USER, prompt)
        started = time.monotonic()
        turn = self._client.turn(folder, session.copilot_session_id, prompt, CopilotMode.EXECUTE,
                                 self._execution_timeout, settings.denied_tools, self._cancel_check(session.id), model=session.model,
                                 mcp=self._access(session))
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
        if status == CopilotSessionStatus.DONE:
            self._message(session, CopilotMessageRole.EVENT,
                          f"Il task è «{STATUS_LABELS[TaskStatus.TO_VERIFY]}»: controlla le modifiche, poi confermalo "
                          "o rimandalo a Copilot dal form del task.")
        self._set_task_status(session, TaskStatus.TO_VERIFY if status == CopilotSessionStatus.DONE else TaskStatus.TODO)
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

    def _refresh_task_folder(self, session: CopilotSession, folder: Path) -> None:
        """The minimal task.md rewritten in the repository (the title may have
        changed since the last turn). Best effort: when the task was deleted
        meanwhile (or the folder cannot be written) the last copy stays and
        the chat goes on."""
        try:
            task = self._data.agent_task(session.project_name, session.task_note)
            task_folder.write(folder, session.task_note, task_folder.minimal_task(session.task_note, task.title, TYPE_LABELS[task.type]))
        except (AppError, OSError):
            log_exception(LogPrefix.COPILOT_SERVICE, "Cartella del task %s non aggiornata", session.task_note)

    def _access(self, session: CopilotSession) -> McpAccess | None:
        """The MCP server and the session's token for a turn; None without a server (or a token)."""
        return McpAccess(self._mcp_url, session.mcp_token) if self._mcp_url and session.mcp_token else None

    def _require_mcp(self) -> None:
        """UpstreamError when the app's MCP server does not answer: without it Copilot cannot read the task."""
        if self._mcp_url and self._mcp_check and (reason := self._mcp_check(self._mcp_url)):
            raise UpstreamError(f"Il server MCP dell'app non risponde su {self._mcp_url}: {reason}. "
                                "Copilot non leggerebbe il task: controlla API_URL e che l'API sia accesa.")

    def _refuse_plan_only(self, session: CopilotSession) -> None:
        """ConflictError when the session's task is plan-only (it is never
        executed). A task deleted meanwhile is not refused here."""
        try:
            task: AgentTask | None = self._data.agent_task(session.project_name, session.task_note)
        except AppError:
            task = None
        if task is not None and task.type.plan_only:
            raise ConflictError("Questo tipo di task non cambia il codice: niente esecuzione. "
                                "Quando la risposta di Copilot va bene, «Salva come nota».")

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
        """``git status`` of the session's repository: the changed files,
        untracked ones too, without the task's folder (``mbare-pilot/``)."""
        changes = self._git.status(session.project_name, session.repository).changes
        return [change.path for change in changes if not task_folder.is_task_path(change.path)]

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


def mcp_url(api_url: str) -> str:
    """Where Copilot reaches the app's MCP server: the API is under /api, the server under /mcp."""
    return f"{api_url.rstrip('/')}/api/mcp/"


def mcp_unreachable(url: str, timeout: float = 5.0) -> str | None:
    """Why the MCP server at ``url`` does not answer a ping; None when it does."""
    try:
        response = httpx.post(url, timeout=timeout, json={"jsonrpc": "2.0", "id": 0, "method": "ping"},
                              headers={"Accept": "application/json, text/event-stream"})
    except httpx.HTTPError as exc:
        return str(exc) or type(exc).__name__
    return None if response.status_code == 200 else f"risposta {response.status_code}"
