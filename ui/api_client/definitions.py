"""Definitions as files (agents, chatbot, automations as YAML in the context
repo), typed: applying them to a project."""
from api_client.http import ApiClient, segment
from api_client.models import SyncReport


class DefinitionsApi:

    def __init__(self, client: ApiClient):
        self._client = client

    def sync(self, project: str) -> SyncReport:
        """Create or update what the project's files define (the file wins)."""
        return SyncReport.model_validate(self._client.post(f"/projects/{segment(project)}/definitions/sync"))
