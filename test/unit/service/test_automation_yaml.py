"""Blocco 05: an automation as YAML in the definitions' format: checked as a
save would (the Architect's proposals), saved with «Salva», exported with
«Esporta YAML» exactly as the definitions write it."""
import pytest
import yaml
from fastapi.testclient import TestClient

from core.app import create_app
from core.container import Container
from core.error import ConflictError, ValidationError
from domain.pipeline import yaml_format
from models.domain.project import Project, ProjectSource

PROPOSAL = """
name: Stato e nota
description: Stato di tutti i repository in una nota.
steps:
  - name: Stato
    function: git_status
    params: {repository: "*"}
  - name: Nota
    function: save_note
    params: {title: "stato-{date}"}
"""


@pytest.fixture
def acme(project_store, tmp_path):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))


def test_check_does_not_save_and_completes_the_chain(acme, pipeline_service):
    pipeline, current = pipeline_service.check_yaml("acme", PROPOSAL)

    assert current is None and pipeline.id is None
    assert [step.name for step in pipeline.steps] == ["Stato", "Nota"]
    assert [(edge.source, edge.target) for edge in pipeline.edges] == [("input", "Stato"), ("Stato", "Nota")]
    assert pipeline_service.list_pipelines("acme") == []


@pytest.mark.parametrize(("text", "error"), [
    ("name: [", "YAML non valido"),
    ("- a\n- b", "un oggetto"),
    ("automations: [{name: A, steps: [{name: S, function: git_status}]}, {name: B, steps: []}]", "una sola automation"),
    ("name: Vuota\nsteps: []", "steps"),
    ("name: X\nsteps: [{name: S, function: non_esiste}]", "non esiste"),
    ("name: X\nsteps: [{name: S, function: git_log, params: {limit: 0}}]", "limit"),
    ("name: X\nsteps: [{name: A, function: git_status}, {name: B, function: git_status}]\n"
     "edges: [{from: input, to: A}, {from: A, to: B}, {from: B, to: A}]", "ciclo"),
    ("name: X\nsteps: [{name: S, agent: inesistente}]", "non esiste più"),
])
def test_what_is_wrong_is_said(acme, pipeline_service, text, error):
    with pytest.raises(ValidationError) as raised:
        pipeline_service.check_yaml("acme", text)
    assert error.lower() in str(raised.value).lower()


def test_save_creates_then_updates_the_same_automation_keeping_step_ids(acme, pipeline_service):
    created = pipeline_service.save_yaml("acme", PROPOSAL)
    _, current = pipeline_service.check_yaml("acme", PROPOSAL.replace("stato-{date}", "stato"))
    assert current is not None and current.id == created.id

    updated = pipeline_service.save_yaml("acme", PROPOSAL.replace("stato-{date}", "stato"))

    assert updated.id == created.id and [step.id for step in updated.steps] == [step.id for step in created.steps]
    assert updated.steps[1].params == {"title": "stato"}
    with pytest.raises(ConflictError):  # another one already has the name
        other = pipeline_service.save_yaml("acme", PROPOSAL.replace("Stato e nota", "Altra"))
        pipeline_service.update_pipeline(other.id, name="Stato e nota", steps=other.steps)


def test_export_is_the_definitions_format_and_reads_back(acme, pipeline_service):
    text = """
automations:
  - name: Rivedi
    active: false
    steps:
      - name: Stato
        function: git_status
      - name: Riassumi
        input: "Riassumi: {input}"
        system_prompt: Riassumi in tre righe.
        model: openrouter/google/gemini-3.1-flash-lite-preview
        max_steps: 2
    edges:
      - {from: input, to: Stato}
      - {from: Stato, to: Riassumi, if: contains, value: modified}
"""
    saved = pipeline_service.save_yaml("acme", text)

    exported = pipeline_service.export_yaml(saved.id)

    assert yaml.safe_load(exported) == yaml.safe_load(text)
    assert yaml_format.to_file(pipeline_service.check_yaml("acme", exported)[0]) == yaml.safe_load(text)["automations"][0]


def test_the_api(stores, project_store, tmp_path):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    with TestClient(create_app(Container(stores=stores))) as client:
        check = client.post("/projects/acme/pipelines/yaml/check", json={"yaml": PROPOSAL}).json()
        assert (check["name"], check["replaces"], check["system"], len(check["edges"])) == ("Stato e nota", None, False, 2)
        assert client.post("/projects/acme/pipelines/yaml/check", json={"yaml": "name: X\nsteps: []"}).status_code == 400

        saved = client.post("/projects/acme/pipelines/yaml", json={"yaml": PROPOSAL}).json()
        assert client.post("/projects/acme/pipelines/yaml/check", json={"yaml": PROPOSAL}).json()["replaces"] == saved["id"]
        assert "name: Stato e nota" in client.get(f"/pipelines/{saved['id']}/yaml").json()["yaml"]
        system = client.post("/projects/acme/pipelines/yaml/check", json={"yaml": PROPOSAL.replace("Stato e nota", "Verifica sviluppo")}).json()
        assert system["system"] is True
