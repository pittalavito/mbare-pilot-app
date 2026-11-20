"""The board of Mbare Pilot from roadmap.yml (the app's default, the data folder's wins)."""
import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from core.error import NotFoundError, ValidationError
from models.domain.roadmap import RoadmapStatus
from service.roadmap_service import RoadmapService
from service.store.definition_store import DefinitionStore


def test_the_app_board_and_the_data_folder_wins(config, tmp_path):
    store = DefinitionStore(tmp_path / "mine", config.app_root / "resource" / "definition")
    roadmap = RoadmapService(store).roadmap()
    assert roadmap.goal == "Demo datapizza" and len(roadmap.items) == 6
    assert [item.status for item in roadmap.items].count(RoadmapStatus.IN_PROGRESS) == 1
    assert roadmap.items[-1].feasibility and {item.kind for item in roadmap.items} >= {"uso", "rag", "integrazione"}

    store.save_definition("roadmap.yml", "goal: Altro\nitems:\n  - title: Una\n    status: done\n")
    mine = RoadmapService(store).roadmap()
    assert mine.goal == "Altro" and [(item.title, item.status) for item in mine.items] == [("Una", RoadmapStatus.DONE)]


def test_no_file_and_a_broken_one(tmp_path):
    store = DefinitionStore(tmp_path / "mine")
    assert RoadmapService(store).roadmap().items == []
    store.save_definition("roadmap.yml", "items:\n  - status: forse\n")
    with pytest.raises(ValidationError, match="roadmap.yml non valido"):
        RoadmapService(store).roadmap()
    store.save_definition("roadmap.yml", "items: [rotto")
    with pytest.raises(ValidationError):
        RoadmapService(store).roadmap()


def test_the_api(stores, config):
    (config.definitions_root / "roadmap.yml").write_text("goal: Demo\nitems:\n  - title: Uno\n", encoding="utf-8")
    with TestClient(create_app(Container(stores=stores))) as http:
        body = http.get("/roadmap").json()
        assert body["goal"] == "Demo" and body["items"][0] == {"id": "uno", "title": "Uno", "description": "", "kind": "", "priority": None,
                                                               "owner": "", "status": "todo", "feasibility": ""}


def test_ids_are_stable_and_unique(tmp_path):
    store = DefinitionStore(tmp_path / "mine")
    store.save_definition("roadmap.yml", "items:\n  - title: Login più veloce\n  - title: Login più veloce\n  - title: Altro\n    id: mio\n")
    assert [item.id for item in RoadmapService(store).roadmap().items] == ["login-piu-veloce", "login-piu-veloce-2", "mio"]


def test_the_ui_writes_the_board_into_the_data_folder(config, tmp_path):
    from models.domain.roadmap import RoadmapCard, RoadmapPriority
    store = DefinitionStore(tmp_path / "mine", config.app_root / "resource" / "definition")
    service = RoadmapService(store)

    board = service.add(RoadmapCard(title=" Bug del login ", kind="bug", priority=RoadmapPriority.HIGH, owner="claude"))
    assert len(board.items) == 7 and board.items[-1].id == "bug-del-login" and board.items[-1].title == "Bug del login"
    mine, app = store.read_layers("roadmap.yml")
    assert "bug-del-login" in mine and "bug-del-login" not in app  # the app's file stays
    assert "id: uso-quotidiano" in mine  # the cards written by hand got their id

    board = service.move("bug-del-login", RoadmapStatus.IN_PROGRESS)
    assert board.items[-1].status is RoadmapStatus.IN_PROGRESS
    board = service.update("bug-del-login", RoadmapCard(title="Bug del login su Windows", status=RoadmapStatus.DONE))
    assert (board.items[-1].id, board.items[-1].title, board.items[-1].priority) == ("bug-del-login", "Bug del login su Windows", None)
    board = service.save_header(" Uso in Aitho ", "")
    assert (board.goal, board.vision) == ("Uso in Aitho", "")
    board = service.delete("bug-del-login")
    assert len(board.items) == 6
    with pytest.raises(NotFoundError):
        service.move("nope", RoadmapStatus.DONE)
    with pytest.raises(NotFoundError):
        service.delete("nope")


def test_the_api_writes(stores, config):
    with TestClient(create_app(Container(stores=stores))) as http:
        created = http.post("/roadmap/items", json={"title": "Uno", "kind": "funzione", "priority": "medium"})
        assert created.status_code == 201 and created.json()["items"][0]["id"] == "uno"
        assert http.post("/roadmap/items/uno/move", json={"status": "done"}).json()["items"][0]["status"] == "done"
        assert http.put("/roadmap/items/uno", json={"title": "Due"}).json()["items"][0]["title"] == "Due"
        assert http.put("/roadmap/header", json={"goal": "G", "vision": "V"}).json()["goal"] == "G"
        assert http.put("/roadmap/items/nope", json={"title": "x"}).status_code == 404
        assert http.post("/roadmap/items/uno/move", json={"status": "forse"}).status_code == 422
        assert http.delete("/roadmap/items/uno").json()["items"] == []
