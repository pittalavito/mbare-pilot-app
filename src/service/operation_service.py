"""«🤖 Automatico» of a pre/post development task (plan 25): its commands,
one after the other in the task's repository, then its automation, without
an agent. ``start`` (the user's click) checks the commands against the
project's allowed list (the others become requests to answer first) and
queues the run in the activity's plan; the worker's ``run_next`` runs it:
first error = stop (the task stays to do, the error on its step), all fine =
the task is done and the round goes on. A task with neither commands nor an
automation is Dev's (the UI opens its panel)."""
from core.error import ConflictError, NotFoundError, ValidationError
from core.observability import LogPrefix, observed
from domain.project.data_paths import note_file_name
from models.domain.note import AgentTask, TaskStatus
from models.domain.pipeline import RunStatus
from models.domain.plan import ActivityPlan, OperationRun, OperationState, PlanTask
from service.command_service import CommandService
from service.pipeline_service import PipelineService
from service.project_data_service import ProjectDataService
from service.store.plan_store import PlanStore

_OUTPUT_CHARS = 20_000
"""The run's log kept in the plan: the last characters."""


class OperationService:

    def __init__(self, plans: PlanStore, project_data: ProjectDataService, commands: CommandService, pipelines: PipelineService):
        self._plans = plans
        self._data = project_data
        self._commands = commands
        self._pipelines = pipelines

    # ----------------------------------------------------------------- start
    @observed(LogPrefix.OPERATION_SERVICE)
    def start(self, project_name: str, activity_name: str, task: str) -> tuple[ActivityPlan, list[str]]:
        """Queues the run; with commands not allowed nothing is queued and they come back (each a request to answer)."""
        plan, planned = self._planned(project_name, activity_name, task)
        current = self._data.agent_task(project_name, task)
        if not current.type.operations:
            raise ValidationError("«Automatico» vale solo per un task pre o post sviluppo.")
        if current.status is TaskStatus.DONE:
            raise ConflictError("Il task è già fatto.")
        if not current.commands and not current.automation.strip():
            raise ValidationError("Il task non ha comandi né automation: fallo fare a Dev.")
        run = plan.operations.get(task)
        if run and run.state in (OperationState.QUEUED, OperationState.RUNNING):
            raise ConflictError("L'automatico di questo task sta già girando.")
        if current.automation.strip():
            self._automation_id(project_name, current.automation)  # it exists, or 404 now (not later in the worker)
        pending = self._commands.pending(project_name, planned.repository, current.commands)
        if pending:
            return plan, pending
        return self._set(plan, task, OperationRun()), []

    # ---------------------------------------------------------------- worker
    def run_next(self) -> bool:
        """The worker's turn: one queued run (its commands, then its automation queued), or a running
        automation that finished. True when it did something."""
        for plan in self._plans.with_operations():
            for task, run in plan.operations.items():
                if run.state is OperationState.QUEUED:
                    self._run(plan, task)
                    return True
                if run.state is OperationState.RUNNING and run.pipeline_run_id is not None and self._finish(plan, task, run):
                    return True
        return False

    @observed(LogPrefix.OPERATION_SERVICE)
    def _run(self, plan: ActivityPlan, task: str) -> None:
        run = OperationRun(state=OperationState.RUNNING)
        plan = self._set(plan, task, run)
        try:
            current = self._data.agent_task(plan.project_name, task)
            planned = next(item for item in plan.tasks if item.task == task)
        except (NotFoundError, StopIteration):
            self._set(plan, task, run.model_copy(update={"state": OperationState.FAILED, "error": "Il task non c'è più."}))
            return
        log: list[str] = []
        for command in current.commands:
            outcome = self._commands.run(plan.project_name, planned.repository, command)
            if not outcome.allowed:
                self._fail(plan, task, log, f"Comando non permesso: {command}. Rispondi alla richiesta e rilancia.")
                return
            log += [f"$ {command}", outcome.output.rstrip(), ""]
            if not outcome.ok:
                self._fail(plan, task, log, f"«{command}» è uscito con {outcome.exit_code}.")
                return
        if not current.automation.strip():
            self._done(plan, task, log)
            return
        try:
            queued = self._pipelines.enqueue(self._automation_id(plan.project_name, current.automation), planned.repository)
        except (NotFoundError, ValidationError) as exc:
            self._fail(plan, task, log, str(exc))
            return
        log.append(f"▶️ Automation «{current.automation}» in coda")
        self._set(plan, task, OperationRun(state=OperationState.RUNNING, output=_cut(log), pipeline_run_id=queued.id))

    def _finish(self, plan: ActivityPlan, task: str, run: OperationRun) -> bool:
        assert run.pipeline_run_id is not None
        try:
            pipeline_run = self._pipelines.get_run(run.pipeline_run_id)
        except NotFoundError:
            self._fail(plan, task, [run.output], "L'esecuzione dell'automation non c'è più.")
            return True
        if pipeline_run.status is RunStatus.DONE:
            self._done(plan, task, [run.output, pipeline_run.output or ""])
            return True
        if pipeline_run.status is RunStatus.FAILED:
            self._fail(plan, task, [run.output], f"Automation fallita: {pipeline_run.error or 'errore'}")
            return True
        return False

    # --------------------------------------------------------------- helpers
    def _done(self, plan: ActivityPlan, task: str, log: list[str]) -> None:
        current: AgentTask = self._data.agent_task(plan.project_name, task)
        if current.status is not TaskStatus.DONE:
            self._data.save_agent_task(plan.project_name, task, current.model_copy(update={"status": TaskStatus.DONE}))
        self._set(plan, task, OperationRun(state=OperationState.DONE, output=_cut(log)))

    def _fail(self, plan: ActivityPlan, task: str, log: list[str], error: str) -> None:
        self._set(plan, task, OperationRun(state=OperationState.FAILED, output=_cut(log), error=error))

    def _set(self, plan: ActivityPlan, task: str, run: OperationRun) -> ActivityPlan:
        """The run in the activity's latest plan (re-read: the user may have changed it meanwhile)."""
        latest = self._plans.latest(plan.project_name, plan.activity) or plan
        return self._plans.save(latest.model_copy(update={"operations": {**latest.operations, task: run}}))

    def _planned(self, project_name: str, activity_name: str, task: str) -> tuple[ActivityPlan, PlanTask]:
        plan = self._plans.latest(project_name, note_file_name(activity_name))
        planned = next((item for item in plan.tasks if item.task == task), None) if plan else None
        if plan is None or planned is None:
            raise NotFoundError(f"Il task {task} non è nel piano.")
        return plan, planned

    def _automation_id(self, project_name: str, name: str) -> int:
        found = next((pipeline for pipeline in self._pipelines.list_pipelines(project_name) if pipeline.name == name.strip()), None)
        if found is None or found.id is None:
            raise NotFoundError(f"Automation non trovata nel progetto: {name.strip()}")
        return found.id


def _cut(log: list[str]) -> str:
    text = "\n".join(part for part in log if part).strip()
    return text if len(text) <= _OUTPUT_CHARS else "…" + text[-_OUTPUT_CHARS:]
