"""Executes pipeline runs, one at a time, for the worker: takes the oldest
queued run and walks its graph in topological order, one step at a time. A
step runs when at least one edge into it let its source's output through
(conditions on the output's text); its ``{input}`` is that output, or all of
them joined under ``## <step>`` when more edges passed. A step no edge lets
through is recorded as SKIPPED. Every step is recorded; the first failing step
fails the run. The run output is the output of the last steps that ran.
Agent steps run through AgentService, so their costs and traces are recorded
like any other run (origin ``pipeline``); function steps run Python code from
the function registry, without an LLM."""
from collections.abc import Callable
from datetime import datetime, timezone

from core.error import AppError, ValidationError
from core.observability import LogPrefix, log_exception, log_warning, observed
from domain.pipeline.graph import join_outputs, passing_targets, topological_order
from function.context import FunctionContext
from function.registry import get_function
from models.domain.agent import AgentDefinition, AgentRunRecord, RunOrigin
from models.domain.pipeline import INPUT_NODE, Pipeline, PipelineRun, PipelineStep, PipelineStepRun, RunStatus, StepKind
from service.agent_service import AgentService
from service.git_service import GitService
from service.masking_service import MaskingService
from service.project_data_service import ProjectDataService
from service.store.pipeline_store import PipelineStore

_ROLE_NAME = "pipeline"
"""Recorded as the role of the runs of a step's own agent (it has no AgentRole)."""
_INTERRUPTED = "Esecuzione interrotta: il worker si è fermato mentre era in corso."


class StepFailed(Exception):
    """A step did not produce an output."""

    def __init__(self, reason: str, agent_run_id: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.agent_run_id = agent_run_id
        """Set when the agent did run (its costs and trace are recorded)."""


class PipelineRunner:

    def __init__(self, pipelines: PipelineStore, agent_service: AgentService, git_service: GitService,
                 project_data_service: ProjectDataService, masking_service: MaskingService | None = None):
        """``masking_service`` registers the sensitive values the function steps
        declare (FunctionResult), so the agent steps after them see aliases."""
        self._pipelines = pipelines
        self._agents = agent_service
        self._git = git_service
        self._project_data = project_data_service
        """The services function steps receive in their FunctionContext."""
        self._masking = masking_service

    def run_next(self, on_claim: Callable[[PipelineRun], None] | None = None) -> PipelineRun | None:
        """Claim and execute the oldest queued run; None when the queue is empty.
        ``on_claim`` is told the run before it executes (the worker's heartbeat)."""
        run = self._pipelines.claim_next_pipeline_run()
        if run is None:
            return None
        if on_claim:
            on_claim(run)
        return self.execute(run)

    def fail_interrupted(self) -> int:
        """Mark as failed the runs left RUNNING by a worker that stopped (call
        at worker startup, before claiming). Returns how many."""
        interrupted = self._pipelines.list_pipeline_runs_by_status(RunStatus.RUNNING)
        for run in interrupted:
            self._finish(run, RunStatus.FAILED, error=_INTERRUPTED)
        return len(interrupted)

    @observed(LogPrefix.PIPELINE_RUNNER)
    def execute(self, run: PipelineRun) -> PipelineRun:
        """Run every step of ``run`` (already RUNNING) and finish it DONE or FAILED."""
        pipeline = self._pipelines.get_pipeline(run.pipeline_id)
        if pipeline is None:
            return self._finish(run, RunStatus.FAILED, error="L'automation è stata eliminata.")

        try:
            order = topological_order(pipeline.steps, pipeline.edges)
        except ValidationError as exc:
            return self._finish(run, RunStatus.FAILED, error=str(exc))
        steps = {step.name: step for step in pipeline.steps}
        outputs: dict[str, str] = {INPUT_NODE: run.input}
        arrived: dict[str, list[str]] = {}  # step -> the sources whose edge into it passed
        for target in passing_targets(INPUT_NODE, run.input, pipeline.edges):
            arrived.setdefault(target, []).append(INPUT_NODE)

        for position, name in enumerate(order):
            step = steps[name]
            sources = arrived.get(name, [])
            if not sources:
                self._skip(run, step, position)
                continue
            previous = join_outputs([(source, outputs[source]) for source in sources])
            step_run = self._pipelines.save_pipeline_step_run(PipelineStepRun(
                pipeline_run_id=run.id,
                step_id=step.id,
                position=position,
                name=step.name,
                kind=step.kind,
                input=step.render_input(previous, run.input, outputs),
                started_at=_now()
            ))
            try:
                output, agent_run_id = self._run_step(pipeline, step, step_run.input, run.input)
            except StepFailed as exc:
                self._finish_step(step_run, RunStatus.FAILED, error=exc.reason, agent_run_id=exc.agent_run_id)
                return self._finish(run, RunStatus.FAILED, error=f"Step {position + 1} ({step.name}): {exc.reason}")
            self._finish_step(step_run, RunStatus.DONE, output=output, agent_run_id=agent_run_id)
            outputs[name] = output
            for target in passing_targets(name, output, pipeline.edges):
                arrived.setdefault(target, []).append(name)
        return self._finish(run, RunStatus.DONE, output=_final_output(order, outputs, pipeline))

    # ------------------------------------------------------------- steps
    def _run_step(self, pipeline: Pipeline, step: PipelineStep, step_input: str, pipeline_input: str) -> tuple[str, str | None]:
        """The step's output and its agent run id (None for functions);
        StepFailed when it has no output."""
        try:
            if step.kind is StepKind.FUNCTION:
                context = FunctionContext(project_name=pipeline.project_name, pipeline_input=pipeline_input, git=self._git, project_data=self._project_data)
                result = get_function(step.function_name).execute(context, step_input, step.params)
                if self._masking is not None:
                    self._masking.register_declared(pipeline.project_name, result)
                return result.text, None
            if step.kind is StepKind.AGENT:
                record = self._agents.run_definition(_agent_definition(pipeline, step), step_input, origin=RunOrigin.PIPELINE)
            else:
                record = self._agents.run(step.agent_config_name, step_input, project_name=pipeline.project_name, origin=RunOrigin.PIPELINE)
        except AppError as exc:
            raise StepFailed(str(exc)) from exc
        except Exception as exc:
            log_exception(LogPrefix.PIPELINE_RUNNER, "Step %s of pipeline %s crashed", step.name, pipeline.name)
            raise StepFailed(f"errore imprevisto: {exc}") from exc
        return _output(record)

    # ------------------------------------------------------------ records
    def _skip(self, run: PipelineRun, step: PipelineStep, position: int) -> None:
        """No edge into ``step`` let anything through: recorded as SKIPPED."""
        self._pipelines.save_pipeline_step_run(PipelineStepRun(
            pipeline_run_id=run.id, step_id=step.id, position=position, name=step.name, kind=step.kind,
            status=RunStatus.SKIPPED, finished_at=_now(),
        ))

    def _finish_step(self, step_run: PipelineStepRun, status: RunStatus, *, output: str | None = None,
                     error: str | None = None, agent_run_id: str | None = None) -> None:
        self._pipelines.save_pipeline_step_run(step_run.model_copy(update={
            "status": status, "output": output, "error": error, "agent_run_id": agent_run_id, "finished_at": _now(),
        }))

    def _finish(self, run: PipelineRun, status: RunStatus, *, output: str | None = None,
                error: str | None = None) -> PipelineRun:
        if error:
            log_warning(LogPrefix.PIPELINE_RUNNER, "Run %s failed: %s", run.id, error)
        self._pipelines.save_pipeline_run(run.model_copy(update={"status": status, "output": output, "error": error, "finished_at": _now()}))
        return self._pipelines.get_pipeline_run(run.id)


def _final_output(order: list[str], outputs: dict[str, str], pipeline: Pipeline) -> str:
    """The output of the steps that ran and fed no other step that ran (the
    ends of the paths taken), joined like a step's inputs."""
    fed = {edge.source for edge in pipeline.edges if edge.target in outputs}
    ends = [(name, outputs[name]) for name in order if name in outputs and name not in fed]
    return join_outputs(ends) if ends else ""


def _output(record: AgentRunRecord) -> tuple[str, str]:
    if not record.ok:
        raise StepFailed(f"l'agente non ha risposto: {record.error}", agent_run_id=record.run_id)
    return record.output, record.run_id


def _agent_definition(pipeline: Pipeline, step: PipelineStep) -> AgentDefinition:
    """A step's own agent, as AgentService runs and records it."""
    agent = step.agent
    return AgentDefinition(
        name=f"pipeline/{pipeline.name}/{step.name}",
        role_name=_ROLE_NAME,
        prompt_id=0,
        prompt_version=agent.prompt_version,
        system_prompt=agent.system_prompt,
        model=agent.model,
        max_steps=agent.max_steps,
        tool_names=agent.tool_names,
        project_name=pipeline.project_name,
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)
