"""The board of Mbare Pilot from roadmap.yml (the app's default, the data folder's wins)."""
import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from core.error import ValidationError
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
        assert body["goal"] == "Demo" and body["items"][0] == {"title": "Uno", "description": "", "kind": "", "owner": "", "status": "todo",
                                                               "feasibility": ""}
