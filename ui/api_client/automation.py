"""Automation endpoints, typed: pipelines, their runs and the functions a
FUNCTION step can call."""
from api_client.http import ApiClient, segment
from api_client.models import Edge, Function, Pipeline, PipelineRun, Step, Worker


class AutomationApi:

    def __init__(self, client: ApiClient):
        self._client = client

    def pipelines(self, project: str) -> list[Pipeline]:
        return [Pipeline.model_validate(item) for item in self._client.get(f"/projects/{segment(project)}/pipelines")]

    def create_pipeline(self, project: str, name: str, description: str, active: bool, steps: list[Step],
                        edges: list[Edge] | None = None) -> Pipeline:
        """``edges`` None or empty = the chain of the steps."""
        body = _body(name, description, active, steps, edges)
        return Pipeline.model_validate(self._client.post(f"/projects/{segment(project)}/pipelines", json=body))

    def update_pipeline(self, pipeline_id: int, name: str, description: str, active: bool, steps: list[Step],
                        edges: list[Edge] | None = None) -> Pipeline:
        body = _body(name, description, active, steps, edges)
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

    def workers(self) -> list[Worker]:
        """The running workers."""
        return [Worker.model_validate(item) for item in self._client.get("/workers")]

    def functions(self) -> list[Function]:
        return [Function.model_validate(item) for item in self._client.get("/functions")]


def _body(name: str, description: str, active: bool, steps: list[Step], edges: list[Edge] | None) -> dict:
    return {"name": name, "description": description, "active": active,
            "steps": [step.model_dump() for step in steps], "edges": [edge.model_dump() for edge in edges or []]}
