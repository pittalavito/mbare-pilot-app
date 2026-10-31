"""Agents, roles, prompts and catalogs API over the in-memory store, seeded
with the defaults (global role/agent ``hello``, model ``openai/gpt-4o``)."""
import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from models.domain.project import Project, ProjectSource


@pytest.fixture
def client(stores, project_store):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    with TestClient(create_app(Container(stores=stores))) as client:
        yield client


def _prompt_id(client, role: str) -> int:
    return client.get(f"/roles/{role}/prompts").json()[0]["id"]


def _agent(client, name: str, role: str = "hello", project: str | None = None, **overrides) -> dict:
    body = {"name": name, "project_name": project, "role_name": role, "prompt_id": _prompt_id(client, role),
            "model": "openai/gpt-4o", "tool_names": ["hello_world"]}
    body.update(overrides)
    return body


# ------------------------------------------------------------------- agents

def test_global_agents_with_status_and_prompt_version(client):
    [agent] = client.get("/agents").json()

    assert (agent["name"], agent["project_name"], agent["prompt_version"]) == ("hello", None, 1)
    assert agent["blocked_reason"] is None


def test_project_scope_listing(client):
    assert client.post("/agents", json=_agent(client, "acme-bot", project="acme")).status_code == 201

    assert [a["name"] for a in client.get("/agents").json()] == ["hello"]
    assert [a["name"] for a in client.get("/agents", params={"project": "acme"}).json()] == ["acme-bot"]
    with_global = client.get("/agents", params={"project": "acme", "include_global": True}).json()
    assert [a["name"] for a in with_global] == ["acme-bot", "hello"]


def test_update_keeps_name_and_scope(client):
    client.post("/agents", json=_agent(client, "acme-bot", project="acme"))
    body = {k: v for k, v in _agent(client, "x", description="nuova", max_steps=7).items()
            if k not in ("name", "project_name")}

    updated = client.put("/agents/acme-bot", json=body).json()

    assert (updated["name"], updated["project_name"], updated["description"], updated["max_steps"]) == \
        ("acme-bot", "acme", "nuova", 7)


def test_delete_agent(client):
    assert client.delete("/agents/hello").status_code == 204
    assert client.get("/agents/hello").status_code == 404
    assert client.delete("/agents/hello").status_code == 404


@pytest.mark.parametrize("overrides, status", [
    ({"name": "hello"}, 409),                    # duplicate name
    ({"tool_names": ["not_a_tool"]}, 400),      # unknown tool
    ({"role_name": "ghost"}, 400),               # unknown role
    ({"model": "not-a-key"}, 400),               # domain model rejects the key
    ({"max_steps": 0}, 400),                     # domain range
])
def test_invalid_agents(client, overrides, status):
    body = _agent(client, "new-bot")
    body.update(overrides)

    response = client.post("/agents", json=body)
    assert response.status_code == status, response.json()
    assert response.json()["detail"]


def test_missing_fields_are_422(client):
    assert client.post("/agents", json={"name": "x"}).status_code == 422


# -------------------------------------------------------------------- roles

def test_roles_create_toggle_and_describe(client):
    created = client.post("/roles", json={"name": "acme-role", "project_name": "acme", "description": "d"})
    assert created.status_code == 201 and created.json()["project_name"] == "acme"
    assert [r["name"] for r in client.get("/roles", params={"project": "acme"}).json()] == ["acme-role"]
    assert [r["name"] for r in client.get("/roles").json()] == ["hello"]

    off = client.patch("/roles/acme-role", json={"active": False}).json()
    assert off["active"] is False
    described = client.patch("/roles/acme-role", json={"description": "nuova"}).json()
    assert (described["description"], described["active"], described["project_name"]) == ("nuova", False, "acme")


def test_inactive_role_blocks_its_agents(client):
    client.patch("/roles/hello", json={"active": False})

    [agent] = client.get("/agents").json()
    assert "disattivato" in agent["blocked_reason"]


def test_role_errors(client):
    assert client.post("/roles", json={"name": "hello"}).status_code == 409
    assert client.post("/roles", json={"name": "r", "project_name": "ghost"}).status_code == 400
    assert client.patch("/roles/ghost", json={"active": False}).status_code == 404
    assert client.get("/roles/ghost/prompts").status_code == 404


# ------------------------------------------------------------------ prompts

def test_prompt_versions(client):
    first = client.post("/roles/hello/prompts", json={"text": "Nuovo prompt"}).json()
    assert (first["created"], first["prompt"]["version"]) == (True, 2)

    same = client.post("/roles/hello/prompts", json={"text": "  Nuovo prompt  "}).json()
    assert (same["created"], same["prompt"]["version"]) == (False, 2)

    assert [p["version"] for p in client.get("/roles/hello/prompts").json()] == [2, 1]
    assert client.post("/roles/hello/prompts", json={"text": "   "}).status_code == 400


def test_prompt_toggle(client):
    v1 = _prompt_id(client, "hello")

    assert client.patch(f"/prompts/{v1}", json={"active": False}).json()["active"] is False
    assert "v1" in client.get("/agents/hello").json()["blocked_reason"]
    assert client.patch("/prompts/9999", json={"active": False}).status_code == 404


# ----------------------------------------------------------------- catalogs

def test_tools_catalog(client):
    tools = {t["name"]: t for t in client.get("/tools").json()}
    assert tools["hello_world"]["available"] is True


def test_model_choices_keep_the_current_model(client):
    body = client.get("/models/choices").json()
    assert "openai/gpt-4o" in body["choices"] and body["choices"] == body["usable"]

    with_current = client.get("/models/choices", params={"current": "openai/retired-model"}).json()
    assert "openai/retired-model" in with_current["choices"]
    assert "openai/retired-model" not in with_current["usable"]
