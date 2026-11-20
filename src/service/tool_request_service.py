"""Requests of tools for Claude Code. A tool that is missing belongs
to the code of mbare-pilot-app, not to a project's repository: the Architetto
writes a **request** (tool ``request_tool``, after the user's ok), of the whole
app; Claude Code on the user's PC, in a clone of mbare-pilot-app, reads the
requests through its own MCP server (controller/dev_mcp_server.py, a token
generated in Admin), writes the tool, opens the PR and marks the request done.
Nothing happens by itself after that: once the PR is merged and the app
restarted, the tool is in the catalog."""
import hashlib
import secrets
from datetime import datetime, timezone

from core.error import NotFoundError, ValidationError
from models.domain.tool_request import ToolRequest, ToolRequestStatus
from service.store.pipeline_store import PipelineStore
from service.store.tool_request_store import ToolRequestStore

_OPEN = (ToolRequestStatus.OPEN, ToolRequestStatus.WORKING)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ToolRequestService:

    def __init__(self, requests: ToolRequestStore, pipelines: PipelineStore | None = None):
        self._requests = requests
        self._pipelines = pipelines

    def create(self, project_name: str, title: str, objective: str, criteria: list[str], automation: str = "", activity: str = "") -> ToolRequest:
        if not title.strip():
            raise ValidationError("Serve un titolo.")
        return self._requests.save(ToolRequest(
            title=title.strip(), objective=objective.strip(), criteria=[text.strip() for text in criteria if text.strip()],
            project_name=project_name, automation=automation.strip(), activity=activity.strip()))

    def list_requests(self, only_open: bool = False) -> list[ToolRequest]:
        """Newest first; ``only_open``: the open ones and the ones being worked."""
        return [request for request in self._requests.list_requests() if not only_open or request.status in _OPEN]

    def get(self, request_id: int) -> ToolRequest:
        request = self._requests.get(request_id)
        if request is None:
            raise NotFoundError(f"Richiesta di tool non trovata: {request_id}")
        return request

    def automation_yaml(self, request: ToolRequest) -> str:
        """The automation that needs the tool, as YAML; ``""`` when there is none (or it is gone)."""
        if not request.automation or self._pipelines is None:
            return ""
        from domain.pipeline.yaml_format import dump
        pipeline = next((item for item in self._pipelines.list_pipelines(request.project_name) if item.name == request.automation), None)
        return dump(pipeline) if pipeline else ""

    def update(self, request_id: int, status: ToolRequestStatus, pr_url: str = "", reason: str = "") -> ToolRequest:
        """In work, done (with the PR) or dismissed (with the reason); open again."""
        request = self.get(request_id)
        if status is ToolRequestStatus.DONE and not pr_url.strip():
            raise ValidationError("Una richiesta fatta vuole il link alla PR.")
        if status is ToolRequestStatus.DISMISSED and not reason.strip():
            raise ValidationError("Scrivi perché la richiesta si scarta.")
        return self._requests.save(request.model_copy(update={
            "status": status, "pr_url": pr_url.strip() or request.pr_url, "reason": reason.strip(), "updated_at": datetime.now(timezone.utc)}))

    # ----------------------------------------------------------------- token
    def new_token(self) -> str:
        """A new token for Claude Code's MCP server (the old one stops working); only its hash is kept."""
        token = secrets.token_urlsafe(32)
        self._requests.save_token_hash(_hash(token))
        return token

    def has_token(self) -> bool:
        return self._requests.token_hash() is not None

    def check_token(self, token: str) -> None:
        """ValidationError unless ``token`` is the current one."""
        expected = self._requests.token_hash()
        if not token or expected is None or not secrets.compare_digest(_hash(token), expected):
            raise ValidationError("Token non valido: generane uno in Admin → Richieste di tool.")
