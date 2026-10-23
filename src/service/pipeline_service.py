"""A project's automations: pipelines of ordered steps (own agent, Library
agent or function), validated on save, and their runs. ``enqueue`` only puts a
run in the queue: the worker (PipelineRunner) executes it."""
from datetime import datetime, timezone

from core.error import ConflictError, NotFoundError, ValidationError
from core.observability import LogPrefix, observed
from function.registry import FUNCTION_REGISTRY, get_function
from function.spec import FunctionSpec
from models.domain.agent import AgentConfig, ToolInfo
from models.domain.pipeline import Pipeline, PipelineRun, PipelineStep, RunStatus, StepKind
from models.domain.worker import WorkerStatus
from service.agent_config_service import AgentConfigService
from service.model_service import require_usable_model
from service.store_service import StoreService


class PipelineService:

    def __init__(self, store_service: StoreService, agent_config_service: AgentConfigService):
        self._store = store_service
        self._agent_configs = agent_config_service

    # ------------------------------------------------------------- pipelines
    def list_pipelines(self, project_name: str) -> list[Pipeline]:
        return self._store.list_pipelines(project_name)

    def get_pipeline(self, pipeline_id: int) -> Pipeline:
        pipeline = self._store.get_pipeline(pipeline_id)
        if pipeline is None:
            raise NotFoundError(f"Automation non trovata: {pipeline_id}")
        return pipeline

    def usable_agents(self, project_name: str) -> list[AgentConfig]:
        """Library agents an AGENT_CONFIG step can use: the global ones and the project's."""
        return self._agent_configs.list_configs(project_name, include_global=True)

    def available_functions(self) -> list[FunctionSpec]:
        """Functions a FUNCTION step can run, sorted by name."""
        return sorted(FUNCTION_REGISTRY.values(), key=lambda spec: spec.name)

    def available_tools(self) -> list[ToolInfo]:
        """Tools an AGENT step's own agent can use."""
        return [tool for tool in self._agent_configs.list_tools() if tool.available]

    @observed(LogPrefix.PIPELINE_SERVICE)
    def create_pipeline(
        self, project_name: str, name: str, *, description: str = "", active: bool = True,
        steps: list[PipelineStep] | None = None,
    ) -> Pipeline:
        if self._store.get_project(project_name) is None:
            raise NotFoundError(f"Progetto non trovato: {project_name}")
        # Steps go in as dicts: after a Streamlit hot reload the caller's
        # PipelineStep class is not this module's, and pydantic rejects it.
        pipeline = Pipeline(
            project_name=project_name, name=name, description=description.strip(), active=active,
            steps=[{**step.model_dump(), "id": None} for step in steps or []],
        )
        self._validate(pipeline)
        return self._store.save_pipeline(pipeline)

    @observed(LogPrefix.PIPELINE_SERVICE)
    def update_pipeline(
        self, pipeline_id: int, *, name: str, description: str = "", active: bool = True,
        steps: list[PipelineStep] | None = None,
    ) -> Pipeline:
        """Everything but the project. Steps keep their id to be updated, the
        others are added, the missing ones removed. An own agent whose system
        prompt changed gets the next ``prompt_version``."""
        current = self.get_pipeline(pipeline_id)
        pipeline = Pipeline.model_validate({
            **current.model_dump(exclude={"steps"}),
            "name": name, "description": description.strip(), "active": active,
            "steps": [step.model_dump() for step in _versioned(current.steps, steps or [])],
            "updated_at": datetime.now(timezone.utc),
        })
        self._validate(pipeline)
        return self._store.save_pipeline(pipeline)

    def delete_pipeline(self, pipeline_id: int) -> bool:
        """With its runs. The agent runs of its steps stay in the history."""
        return self._store.delete_pipeline(pipeline_id)

    # ------------------------------------------------------------------ runs
    @observed(LogPrefix.PIPELINE_SERVICE)
    def enqueue(self, pipeline_id: int, pipeline_input: str = "") -> PipelineRun:
        """Queue a run of the pipeline: the worker picks it up."""
        pipeline = self.get_pipeline(pipeline_id)
        if not pipeline.active:
            raise ValidationError(f"L'automation {pipeline.name} è disattivata.")
        if not pipeline.steps:
            raise ValidationError(f"L'automation {pipeline.name} non ha step.")
        self._validate(pipeline)
        return self._store.save_pipeline_run(PipelineRun(pipeline_id=pipeline.id, input=pipeline_input))

    def list_runs(self, pipeline_id: int, limit: int = 20) -> list[PipelineRun]:
        """With their steps, newest first."""
        return self._store.list_pipeline_runs(pipeline_id, limit)

    def get_run(self, run_id: int) -> PipelineRun:
        run = self._store.get_pipeline_run(run_id)
        if run is None:
            raise NotFoundError(f"Esecuzione non trovata: {run_id}")
        return run

    def delete_run(self, run_id: int) -> bool:
        """Remove a run from the history (queued, done or failed; not while
        running). The agent runs of its steps stay in Observability."""
        run = self.get_run(run_id)
        if run.status is RunStatus.RUNNING:
            raise ValidationError("L'esecuzione è in corso: aspetta che finisca per eliminarla.")
        return self._store.delete_pipeline_run(run_id)

    # ------------------------------------------------------------ workers
    def heartbeat(self, status: WorkerStatus) -> None:
        """A worker says it is alive (call every few seconds, well under the keyspace TTL)."""
        self._store.save_worker_heartbeat(status)

    def workers(self) -> list[WorkerStatus]:
        """The running workers (their heartbeat has not expired), oldest first."""
        return sorted(self._store.list_workers(), key=lambda worker: worker.started_at)

    def worker_stopped(self, worker_id: str) -> None:
        """A worker shutting down cleanly: gone at once, without waiting for the TTL."""
        self._store.delete_worker(worker_id)

    # ------------------------------------------------------------- helpers
    def _validate(self, pipeline: Pipeline) -> None:
        for other in self._store.list_pipelines(pipeline.project_name):
            if other.name.lower() == pipeline.name.lower() and other.id != pipeline.id:
                raise ConflictError(f"Esiste già un'automation chiamata {other.name} in questo progetto.")
        tools = {tool.name for tool in self.available_tools()}
        for position, step in enumerate(pipeline.steps, start=1):
            label = f"Step {position} ({step.name})"
            if step.kind is StepKind.AGENT:
                if step.agent is None:
                    raise ValidationError(f"{label}: configura il suo agente.")
                try:
                    require_usable_model(self._store, step.agent.model)
                except ValidationError as exc:
                    raise ValidationError(f"{label}: {exc}") from exc
                unavailable = [name for name in step.agent.tool_names if name not in tools]
                if unavailable:
                    raise ValidationError(f"{label}: tool non disponibili: {', '.join(unavailable)}")
            elif step.kind is StepKind.AGENT_CONFIG:
                if not step.agent_config_name:
                    raise ValidationError(f"{label}: scegli l'agente della Libreria.")
                agent = self._store.get_agent_config(step.agent_config_name)
                if agent is None:
                    raise ValidationError(f"{label}: l'agente {step.agent_config_name} non esiste più.")
                if agent.project_name not in (None, pipeline.project_name):
                    raise ValidationError(f"{label}: l'agente {agent.name} appartiene al progetto {agent.project_name}.")
            else:
                try:
                    get_function(step.function_name).validate_params(step.params)
                except ValidationError as exc:
                    raise ValidationError(f"{label}: {exc}") from exc


def _versioned(current: list[PipelineStep], steps: list[PipelineStep]) -> list[PipelineStep]:
    """``steps`` with the prompt version of their own agent: kept when the
    prompt is unchanged, incremented when it changed, 1 for new steps."""
    previous = {step.id: step for step in current}
    result = []
    for step in steps:
        before = previous.get(step.id)
        step = step.model_copy(update={"id": step.id if before else None})
        if step.agent is not None:
            version = 1
            if before is not None and before.agent is not None:
                changed = before.agent.system_prompt != step.agent.system_prompt.strip()
                version = before.agent.prompt_version + (1 if changed else 0)
            step = step.model_copy(update={"agent": step.agent.model_copy(update={"prompt_version": version})})
        result.append(step)
    return result
