"""The UI's AgentsApi end-to-end against the real FastAPI app (in-memory store,
seeded with the global role/agent ``hello``)."""
import pytest
from fastapi.testclient import TestClient

from api_client.agents import AgentsApi
from api_client.http import ApiClient, ApiError
from core.app import create_app
from core.container import Container
from models.domain.project import Project, ProjectSource


@pytest.fixture
def agents(store_service):
    store_service.save_project(Project(name="acme corp", source=ProjectSource.FOLDER, root_path="/code/acme"))
    with TestClient(create_app(Container(store_service=store_service))) as test_client:
        client = ApiClient("http://testserver")
        client._client = test_client  # TestClient is an httpx.Client bound to the app
        yield AgentsApi(client)


def test_agents_contract_end_to_end(agents):
    [hello] = agents.agents(None)
    assert hello.name == "hello" and hello.blocked_reason is None

    role = agents.create_role("acme-role", "acme corp", "di progetto")
    assert role.project_name == "acme corp"
    version = agents.create_prompt_version("acme-role", "Sei un revisore.")
    assert (version.created, version.prompt.version) == (True, 1)
    assert agents.create_prompt_version("acme-role", "Sei un revisore.").created is False

    model = agents.model_choices().usable[0]
    created = agents.create_agent({
        "name": "acme-reviewer", "project_name": "acme corp", "role_name": "acme-role",
        "prompt_id": version.prompt.id, "model": model, "max_steps": 3, "tool_names": ["hello_world"],
    })
    assert created.project_name == "acme corp" and created.prompt_version == 1
    assert [a.name for a in agents.agents("acme corp")] == ["acme-reviewer"]
    assert {r.name for r in agents.roles("acme corp", include_global=True)} == {"acme-role", "hello"}

    updated = agents.update_agent("acme-reviewer", {
        "description": "nuova", "role_name": "acme-role", "prompt_id": version.prompt.id,
        "model": model, "max_steps": 5, "tool_names": [],
    })
    assert (updated.description, updated.max_steps, updated.tool_names) == ("nuova", 5, [])

    agents.set_role_active("acme-role", False)
    assert "disattivato" in agents.agent("acme-reviewer").blocked_reason
    agents.set_role_active("acme-role", True)
    agents.set_prompt_active(version.prompt.id, False)
    assert agents.prompts("acme-role")[0].active is False

    agents.delete_agent("acme-reviewer")
    with pytest.raises(ApiError) as exc:
        agents.agent("acme-reviewer")
    assert exc.value.status == 404
    assert any(tool.name == "hello_world" for tool in agents.tools())


def test_api_errors_reach_the_ui_as_messages(agents):
    with pytest.raises(ApiError, match="Esiste già un ruolo"):
        agents.create_role("hello", None)
