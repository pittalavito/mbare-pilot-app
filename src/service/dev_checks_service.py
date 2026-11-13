"""The checks around a development task delegated to Copilot (blocco 09),
deterministic: the project's automations «Prepara sviluppo» and «Verifica
sviluppo» (definitions, global-automation.yml), made of functions.

- ``prepare(project, targets)``: at the delegation, before Copilot's first
  turn (in the API, while the user waits). Its input is one line per
  repository to get ready (domain/dev/inputs.py). Copilot starts only if it
  goes well.
- ``verify(project, repository, task)``: in the worker, when a development
  goes «to verify». Its input says the repository, the task and which tests
  (the task's choice, or the project's default).

Each runs **at once** in the calling process (not queued: a run is created
RUNNING and executed with the PipelineRunner, so the worker never claims it),
and stays in the automation's history. A project without the automation (or
with it switched off) skips the check. The result's text is every step's
output, or where it stopped and why.

Also the tests' settings (``settings`` / ``save_settings``): the command
detected for each repository of the project, the one written in its place
and the default scope."""
import json
from datetime import datetime, timezone

from core.error import NotFoundError, ValidationError
from core.observability import LogPrefix, log_info
from domain.dev import tests
from domain.dev.inputs import render_prepare, render_verify
from models.domain.dev import (
    PREPARE_AUTOMATION,
    VERIFY_AUTOMATION,
    DevCheck,
    DevSettings,
    PrepareTarget,
    RepositoryTests,
    TestScope,
)
from models.domain.pipeline import Pipeline, PipelineRun, RunStatus, StepKind
from service.git_service import GitService
from service.pipeline_runner import PipelineRunner
from service.project_data_service import ProjectDataService
from service.store.pipeline_store import PipelineStore


class DevChecksService:

    def __init__(self, pipelines: PipelineStore, runner: PipelineRunner, git: GitService, project_data: ProjectDataService):
        self._pipelines = pipelines
        self._runner = runner
        self._git = git
        self._data = project_data

    # ---------------------------------------------------------------- checks
    def prepare(self, project_name: str, targets: list[PrepareTarget]) -> DevCheck:
        return self._run(project_name, PREPARE_AUTOMATION, render_prepare(targets))

    def verify(self, project_name: str, repository: str, task_note: str) -> DevCheck:
        scope = self._data.agent_task(project_name, task_note).tests or self._data.test_scope(project_name)
        return self._run(project_name, VERIFY_AUTOMATION, render_verify(repository, task_note, scope))

    def has(self, project_name: str, automation: str) -> bool:
        """The project has the automation, switched on."""
        return any(pipeline.name == automation and pipeline.active for pipeline in self._pipelines.list_pipelines(project_name))

    def prepare_learned(self, project_name: str, pipeline_id: int, fields: dict[str, str]) -> DevCheck:
        """An automation learned from the Operator (plan 11), with its fields (filled from the task)."""
        pipeline = self._pipelines.get_pipeline(pipeline_id)
        if pipeline is None or pipeline.project_name != project_name:
            raise NotFoundError(f"Automation non trovata: {pipeline_id}")
        if not pipeline.active:
            raise ValidationError(f"L'automation {pipeline.name} è disattivata.")
        return self._execute(pipeline, json.dumps({name: fields.get(name, "") for name in pipeline.fields}))

    def _run(self, project_name: str, automation: str, text: str) -> DevCheck:
        pipeline = next((item for item in self._pipelines.list_pipelines(project_name) if item.name == automation and item.active), None)
        if pipeline is None or pipeline.id is None:
            return DevCheck(ok=True, skipped=True, text=f"Il progetto non ha l'automation «{automation}» (attiva): niente controlli.")
        return self._execute(pipeline, text)

    def _execute(self, pipeline: Pipeline, text: str) -> DevCheck:
        assert pipeline.id is not None
        run = self._pipelines.save_pipeline_run(PipelineRun(
            pipeline_id=pipeline.id, input=text, status=RunStatus.RUNNING, started_at=datetime.now(timezone.utc)))
        finished = self._runner.execute(run)
        outputs = [f"✓ {step.name}" if step.kind is StepKind.TOOL else step.output.strip()  # a tool's output is JSON: its name says enough
                   for step in finished.steps if step.status == RunStatus.DONE and (step.output or "").strip()]
        ok = finished.status == RunStatus.DONE
        log_info(LogPrefix.PIPELINE_RUNNER, "%s · %s: %s", pipeline.project_name, pipeline.name, "ok" if ok else finished.error)
        text_out = "\n\n".join(outputs) if ok else "\n\n".join([*outputs, finished.error or "fallita"])
        return DevCheck(ok=ok, text=text_out, run_id=finished.id)

    # -------------------------------------------------------------- settings
    def settings(self, project_name: str) -> DevSettings:
        commands = self._data.test_commands(project_name)
        repositories = []
        for repository in self._git.repositories(project_name):
            root = self._git.repository_folder(project_name, repository.path)
            files = {path.name for path in root.iterdir()}
            kind = tests.detect(files)
            repositories.append(RepositoryTests(repository=repository.path, kind=kind, detected_command=tests.default_command(kind, files),
                                                command=commands.get(repository.path, "")))
        return DevSettings(test_scope=self._data.test_scope(project_name), repositories=repositories)

    def operator_chatbot_id(self, project_name: str) -> int | None:
        """The Operator chosen for the preparation (None = the project's first one)."""
        return self._data.operator_chatbot_id(project_name)

    def save_operator(self, project_name: str, chatbot_id: int | None) -> None:
        self._data.save_operator_chatbot_id(project_name, chatbot_id)

    def save_settings(self, project_name: str, scope: TestScope, commands: dict[str, str]) -> DevSettings:
        self._data.save_test_settings(project_name, scope, commands)
        return self.settings(project_name)
