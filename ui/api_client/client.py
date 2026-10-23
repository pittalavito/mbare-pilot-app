"""API facade: one import point for the views. ``Api`` groups the endpoint
clients; there is one per Streamlit server process."""
from api_client.admin import AdminApi
from api_client.agents import AgentsApi
from api_client.atlassian import AtlassianApi
from api_client.automation import AutomationApi
from api_client.chat import ChatApi
from api_client.git import GitApi
from api_client.http import ApiClient, ApiError, ApiUnavailable
from api_client.masking import MaskingApi
from api_client.project_data import ProjectDataApi
from api_client.projects import ProjectsApi

__all__ = ["Api", "ApiError", "ApiUnavailable"]


class Api:

    def __init__(self, base_url: str):
        self.http = ApiClient(base_url)
        self.projects = ProjectsApi(self.http)
        self.agents = AgentsApi(self.http)
        self.chat = ChatApi(self.http)
        self.data = ProjectDataApi(self.http)
        self.git = GitApi(self.http)
        self.automation = AutomationApi(self.http)
        self.atlassian = AtlassianApi(self.http)
        self.admin = AdminApi(self.http)
        self.masking = MaskingApi(self.http)

    def health(self) -> bool:
        try:
            return self.http.get("/health").get("status") == "ok"
        except ApiError:
            return False
