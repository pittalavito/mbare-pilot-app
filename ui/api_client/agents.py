"""Agents, roles, prompt versions, tools and model choices endpoints, typed.
``scope`` None = global (Library), otherwise a project name."""
from urllib.parse import quote

from api_client.http import ApiClient
from api_client.models import Agent, ModelChoices, Prompt, PromptVersion, Role, Tool


class AgentsApi:

    def __init__(self, client: ApiClient):
        self._client = client

    # ------------------------------------------------------------- agents
    def agents(self, scope: str | None, include_global: bool = False) -> list[Agent]:
        params = {"project": scope, "include_global": include_global} if scope else None
        return [Agent.model_validate(item) for item in self._client.get("/agents", params=params)]

    def agent(self, name: str) -> Agent:
        return Agent.model_validate(self._client.get(f"/agents/{_q(name)}"))

    def create_agent(self, body: dict) -> Agent:
        """``body``: name, project_name, description, role_name, prompt_id, model, max_steps, tool_names."""
        return Agent.model_validate(self._client.post("/agents", json=body))

    def update_agent(self, name: str, body: dict) -> Agent:
        """``body``: as create, without name and project_name (fixed at creation)."""
        return Agent.model_validate(self._client.put(f"/agents/{_q(name)}", json=body))

    def delete_agent(self, name: str) -> None:
        self._client.delete(f"/agents/{_q(name)}")

    # -------------------------------------------------------------- roles
    def roles(self, scope: str | None, include_global: bool = False) -> list[Role]:
        params = {"project": scope, "include_global": include_global} if scope else None
        return [Role.model_validate(item) for item in self._client.get("/roles", params=params)]

    def create_role(self, name: str, scope: str | None, description: str = "") -> Role:
        body = {"name": name, "project_name": scope, "description": description}
        return Role.model_validate(self._client.post("/roles", json=body))

    def set_role_active(self, name: str, active: bool) -> Role:
        return Role.model_validate(self._client.patch(f"/roles/{_q(name)}", json={"active": active}))

    # ------------------------------------------------------------ prompts
    def prompts(self, role_name: str) -> list[Prompt]:
        """Newest first."""
        return [Prompt.model_validate(item) for item in self._client.get(f"/roles/{_q(role_name)}/prompts")]

    def create_prompt_version(self, role_name: str, text: str) -> PromptVersion:
        return PromptVersion.model_validate(self._client.post(f"/roles/{_q(role_name)}/prompts", json={"text": text}))

    def set_prompt_active(self, prompt_id: int, active: bool) -> Prompt:
        return Prompt.model_validate(self._client.patch(f"/prompts/{prompt_id}", json={"active": active}))

    # ----------------------------------------------------------- catalogs
    def tools(self) -> list[Tool]:
        return [Tool.model_validate(item) for item in self._client.get("/tools")]

    def model_choices(self, current: str | None = None) -> ModelChoices:
        params = {"current": current} if current else None
        return ModelChoices.model_validate(self._client.get("/models/choices", params=params))


def _q(value: str) -> str:
    return quote(value, safe="")
