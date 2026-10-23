"""Automation endpoints, typed: pipelines, their runs and the functions a
FUNCTION step can call."""
from api_client.http import ApiClient, segment
from api_client.models import Function, Pipeline, PipelineRun, Step


class AutomationApi:

    def __init__(self, client: ApiClient):
        self._client = client

    def pipelines(self, project: str) -> list[Pipeline]:
        return [Pipeline.model_validate(item) for item in self._client.get(f"/projects/{segment(project)}/pipelines")]

    def create_pipeline(self, project: str, name: str, description: str, active: bool, steps: list[Step]) -> Pipeline:
        body = _body(name, description, active, steps)
        return Pipeline.model_validate(self._client.post(f"/projects/{segment(project)}/pipelines", json=body))

    def update_pipeline(self, pipeline_id: int, name: str, description: str, active: bool, steps: list[Step]) -> Pipeline:
        body = _body(name, description, active, steps)
        return Pipeline.model_validate(self._client.put(f"/pipelines/{pipeline_id}", json=body))

    def delete_pipeline(self, pipeline_id: int) -> None:
        self._client.delete(f"/pipelines/{pipeline_id}")

    def runs(self, pipeline_id: int) -> list[PipelineRun]:
        """Newest first, with their steps."""
        return [PipelineRun.model_validate(item) for item in self._client.get(f"/pipelines/{pipeline_id}/runs")]

    def enqueue(self, pipeline_id: int, pipeline_input: str) -> PipelineRun:
        body = {"input": pipeline_input}
        return PipelineRun.model_validate(self._client.post(f"/pipelines/{pipeline_id}/runs", json=body))

    def delete_run(self, run_id: int) -> None:
        self._client.delete(f"/pipeline-runs/{run_id}")

    def waiting_too_long(self) -> bool:
        """Some run is queued for too long: the worker is probably not running."""
        return self._client.get("/pipeline-runs/waiting")["waiting_too_long"]

    def functions(self) -> list[Function]:
        return [Function.model_validate(item) for item in self._client.get("/functions")]


def _body(name: str, description: str, active: bool, steps: list[Step]) -> dict:
    return {"name": name, "description": description, "active": active,
            "steps": [step.model_dump() for step in steps]}
