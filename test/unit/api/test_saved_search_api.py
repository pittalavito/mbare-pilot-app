"""Plan 34: saved searches («regex parlanti») — the defaults of code-searches.yml,
the project's own (they replace a default with the same name) and «✨ Regex»
(one structured call to the agent ``regex``, fake model)."""
import pytest
import yaml
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from fakes import FakeStructuredClient as FakeClient
from models.domain.code_search import RegexAnswer
from models.domain.project import Project, ProjectSource

DEFAULTS = {"searches": [{"name": "TODO", "query": r"\bTODO\b"}, {"name": "FIXME", "query": "FIXME", "regex": False}]}


@pytest.fixture
def model():
    return FakeClient(RegexAnswer(regex=r"(?i)//\s*mbare", explanation="I commenti mbare.", example="// MBARE fare il login"))


@pytest.fixture
def client(stores, config, monkeypatch, project_store, tmp_path, model, default_chatbots):
    (config.definitions_root / "code-searches.yml").write_text(yaml.safe_dump(DEFAULTS), encoding="utf-8")
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    container = Container(stores=stores)
    monkeypatch.setattr(container.chat_service, "get_client", lambda key: model)
    with TestClient(create_app(container)) as client:
        yield client


def names(searches):
    return [(search["name"], search["origin"]) for search in searches]


def test_the_defaults_then_the_project_s_own(client):
    assert names(client.get("/projects/acme/code-search/saved").json()) == [("TODO", "app"), ("FIXME", "app")]

    after = client.put("/projects/acme/code-search/saved", json={"name": " Commenti   MBARE ", "query": "MBARE", "files": " *.java "}).json()

    assert names(after) == [("TODO", "app"), ("FIXME", "app"), ("Commenti MBARE", "progetto")]
    assert after[2]["files"] == "*.java" and after[2]["regex"] is True


def test_the_project_s_search_replaces_the_default_and_removed_it_comes_back(client):
    client.put("/projects/acme/code-search/saved", json={"name": "TODO", "query": "TODO|todo"})

    [todo, _] = client.get("/projects/acme/code-search/saved").json()
    assert (todo["origin"], todo["query"]) == ("progetto", "TODO|todo")

    back = client.delete("/projects/acme/code-search/saved/TODO").json()
    assert back[0] == {"name": "TODO", "query": r"\bTODO\b", "regex": True, "files": "", "description": "", "origin": "app"}


def test_renaming_and_deleting(client):
    client.put("/projects/acme/code-search/saved", json={"name": "A", "query": "a"})

    after = client.put("/projects/acme/code-search/saved", json={"name": "B", "query": "b", "replacing": "A"}).json()

    assert names(after)[2:] == [("B", "progetto")]
    assert client.delete("/projects/acme/code-search/saved/A").status_code == 404
    assert client.delete("/projects/acme/code-search/saved/FIXME").status_code == 404  # a default: not the project's


def test_a_broken_regex_is_a_400_plain_text_is_not(client):
    assert client.put("/projects/acme/code-search/saved", json={"name": "X", "query": "(("}).status_code == 400
    assert client.put("/projects/acme/code-search/saved", json={"name": "X", "query": "((", "regex": False}).status_code == 200


def test_a_broken_defaults_file_is_a_400(client, config):
    (config.definitions_root / "code-searches.yml").write_text("searches: [{name: x}]", encoding="utf-8")

    assert client.get("/projects/acme/code-search/saved").status_code == 400


def test_without_the_file_no_defaults_and_an_unknown_project_is_a_404(client, config):
    (config.definitions_root / "code-searches.yml").unlink()

    assert client.get("/projects/acme/code-search/saved").json() == []
    assert client.get("/projects/nope/code-search/saved").status_code == 404


def test_the_app_s_defaults_are_valid():
    from pathlib import Path

    from models.domain.code_search import SavedSearchFile
    text = (Path(__file__).parents[3] / "resource" / "definition" / "code-searches.yml").read_text(encoding="utf-8")
    searches = SavedSearchFile.model_validate(yaml.safe_load(text)).searches
    assert {"TODO", "FIXME", "Commenti Mbare Pilot"} <= {search.name for search in searches}


def test_regex_from_words(client, model, stores):
    proposal = client.post("/projects/acme/code-search/regex", json={"description": " i commenti mbare "}).json()

    assert (proposal["regex"], proposal["valid"], proposal["example_matches"]) == (r"(?i)//\s*mbare", True, True)
    [call] = model.calls
    assert call["system_prompt"].startswith("Da quello che voglio cercare") and "i commenti mbare" in call["input"]
    [run] = [run for run in stores.runs.list_runs() if run.run_id == proposal["run_id"]]
    assert (run.origin, run.config_name) == ("regex", "regex")


def test_a_broken_or_unmatched_regex_is_said(client, model):
    model.answer = RegexAnswer(regex="((", explanation="x", example="y")
    assert client.post("/projects/acme/code-search/regex", json={"description": "x"}).json()["valid"] is False

    model.answer = RegexAnswer(regex="abc", example="xyz")
    proposal = client.post("/projects/acme/code-search/regex", json={"description": "x"}).json()
    assert (proposal["valid"], proposal["example_matches"]) == (True, False)


def test_regex_errors(client, model):
    assert client.post("/projects/acme/code-search/regex", json={"description": " "}).status_code == 400
    model.answer = RegexAnswer()
    assert client.post("/projects/acme/code-search/regex", json={"description": "x"}).status_code == 502
    model.error = RuntimeError("giù")
    assert client.post("/projects/acme/code-search/regex", json={"description": "x"}).status_code == 502
