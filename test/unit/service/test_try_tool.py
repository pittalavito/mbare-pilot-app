"""Admin → Tool: a tool tried by hand on a project, no LLM."""
import pytest
from datapizza.tools import Tool

from core.container import Container
from core.error import NotFoundError, ValidationError
from models.domain.project import Project, ProjectSource
from tool.registry import TOOL_REGISTRY
from tool.spec import ToolSpec


def test_trying_a_tool_by_hand(stores, project_store, tmp_path, monkeypatch):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    container = Container(stores=stores)
    service = container.agent_service

    assert service.try_tool("save_note", "acme", {"title": "Prova", "content": "ciao"}).text.startswith("Nota salvata")
    assert "Argomenti non validi" in service.try_tool("hello_world", "acme", {"nome": "x"}).error
    assert service.try_tool("hello_world", "acme", {"name": "Ada"}).response == "Hello, Ada!"
    with pytest.raises(NotFoundError):
        service.try_tool("nessuno", "acme", {})

    plain = Tool(func=lambda: "solo testo", name="plain", description="x", properties={}, required=[])
    monkeypatch.setitem(TOOL_REGISTRY, "plain", ToolSpec("plain", "x", lambda context: plain))
    assert service.try_tool("plain", "acme", {}).text == "solo testo"

    def boom():
        raise ValidationError("rotto")
    broken = Tool(func=boom, name="broken", description="x", properties={}, required=[])
    monkeypatch.setitem(TOOL_REGISTRY, "broken", ToolSpec("broken", "x", lambda context: broken))
    assert service.try_tool("broken", "acme", {}).error == "rotto"
