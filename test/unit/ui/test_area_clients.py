"""The UI's chat, data, automation, Atlassian and Admin clients end-to-end
against the real FastAPI app (in-memory store, fake agents). Project name
with a space, to check the URL encoding."""
import pytest
from fastapi.testclient import TestClient

from api_client.client import Api
from api_client.http import ApiError
from api_client.models import Step, StepAgent
from core.app import create_app
from core.container import Container
from fakes import FakeAgent, make_run_record
from models.domain.atlassian import ConfluencePage, ConfluenceSearchHit, ConfluenceSpace, JiraIssue
from models.domain.project import Project, ProjectSource
from service import agent_service as agent_service_module
from service.atlassian_service import AtlassianSite

PROJECT = "acme corp"
MODEL = "openai/gpt-4o"


@pytest.fixture
def api(store_service, tmp_path, monkeypatch):
    store_service.save_project(Project(name=PROJECT, source=ProjectSource.FOLDER, root_path=str(tmp_path)))
    monkeypatch.setattr(agent_service_module.AgentFactory, "create_agent",
                        staticmethod(lambda definition, client, tools: FakeAgent(None)))
    container = Container(store_service=store_service)
    monkeypatch.setattr(container.chat_service, "get_client", lambda model: object())
    with TestClient(create_app(container)) as test_client:
        api = Api("http://testserver")
        api.http._client = test_client  # TestClient is an httpx.Client bound to the app
        yield api


def test_chat(api):
    bot = api.chat.create_chatbot(PROJECT, {"name": "Bot", "system_prompt": "Ciao.", "model": MODEL})
    conversation = api.chat.new_conversation(bot.id)

    reply = api.chat.send(conversation.id, "Ciao")

    assert reply.role == "assistant"
    assert [m.role for m in api.chat.messages(conversation.id)] == ["user", "assistant"]
    assert api.chat.conversations(bot.id)[0].title == "Ciao"
    with pytest.raises(ApiError) as error:
        api.chat.send(conversation.id, "")
    assert error.value.status == 400


def test_chat_cache(api):
    bot = api.chat.create_chatbot(PROJECT, {"name": "Bot", "system_prompt": "Ciao.", "model": MODEL})
    steps = [Step(name="Scrivi", kind="agent", input_template="{input}",
                  agent=StepAgent(system_prompt="Scrivi.", model=MODEL))]
    report = api.automation.create_pipeline(PROJECT, "Report", "", True, steps)
    conversation = api.chat.new_conversation(bot.id)
    api.chat.send(conversation.id, "lancia il report")
    message = api.chat.messages(conversation.id)[0]

    route = api.chat.add_route(message.id, report.id, "oggi")
    reply = api.chat.send(conversation.id, "Lancia il report")

    assert (route.message_id, route.pipeline_id, route.pipeline_input) == (message.id, report.id, "oggi")
    assert reply.content.startswith("⚡ Ho lanciato l'automation Report") and reply.run_id is None
    assert api.chat.routes(bot.id)[0].hits == 1
    with pytest.raises(ApiError) as error:
        api.chat.add_route(message.id, report.id)
    assert error.value.status == 409
    api.chat.delete_route(route.id)
    assert api.chat.routes(bot.id) == []


def test_definitions_sync(api, store_service):
    store_service.save_definition("project/acme-corp/automation.yml",
                                  "automations:\n  - name: Semplice\n    steps:\n      - {name: Stato, function: git_status}\n")

    [item] = api.definitions.sync(PROJECT).items

    assert (item.kind, item.file, item.name, item.outcome) == (
        "automation", "project/acme-corp/automation.yml", "Semplice", "created",
    )
    assert [pipeline.name for pipeline in api.automation.pipelines(PROJECT)] == ["Semplice"]


def test_notes_and_files(api):
    note = api.data.save_note(PROJECT, "Setup", "# Setup")
    assert api.data.read_note(PROJECT, note.name) == "# Setup"

    api.data.save_file(PROJECT, "dati 1.bin", b"\x00\x01")
    assert api.data.read_file(PROJECT, "dati 1.bin") == b"\x00\x01"
    api.data.delete_file(PROJECT, "dati 1.bin")
    assert api.data.files(PROJECT) == []


def test_automation(api):
    steps = [Step(name="Scrivi", kind="agent", input_template="{input}",
                  agent=StepAgent(system_prompt="Scrivi.", model=MODEL))]
    pipeline = api.automation.create_pipeline(PROJECT, "Flow", "", True, steps)
    assert pipeline.steps[0].agent.model == MODEL

    run = api.automation.enqueue(pipeline.id, "ciao")
    assert not run.finished and api.automation.runs(pipeline.id)[0].id == run.id
    assert api.automation.workers() == []
    assert "git_status" in {spec.name for spec in api.automation.functions()}


def test_atlassian(api):
    assert api.atlassian.settings(PROJECT) is None
    saved = api.atlassian.save(PROJECT, {"base_url": "https://acme.atlassian.net", "email": "a@b.it", "api_token": "x"})
    assert saved.has_token
    api.atlassian.remove(PROJECT)
    assert api.atlassian.settings(PROJECT) is None


def test_atlassian_reads(api, monkeypatch):
    site = AtlassianSite(_FakeJira(), _FakeConfluence(), confluence_space_key="DOC")
    monkeypatch.setattr(api.http._client.app.state.container.atlassian_service, "site", lambda project: site)

    assert api.atlassian.issue(PROJECT, " proj-7 ").key == "PROJ-7"
    [listed] = api.atlassian.pages(PROJECT)
    assert api.atlassian.page(PROJECT, listed.id).body == "Testo."
    assert api.atlassian.search_pages(PROJECT, "setup")[0].title == "Setup"


def test_atlassian_favorites(api):
    api.atlassian.save(PROJECT, {"base_url": "https://acme.atlassian.net", "email": "a@b.it", "api_token": "x"})
    issue = api.atlassian.add_favorite(PROJECT, "jira_issue", "proj-1", "Bug", "https://acme.atlassian.net/browse/PROJ-1")
    api.atlassian.add_favorite(PROJECT, "confluence_page", "9", "Setup", "")

    assert [(f.kind, f.ref) for f in api.atlassian.favorites(PROJECT)] == [("jira_issue", "PROJ-1"), ("confluence_page", "9")]
    api.atlassian.remove_favorite(PROJECT, issue.id)
    assert [f.ref for f in api.atlassian.favorites(PROJECT)] == ["9"]


class _FakeJira:
    def get_issue(self, key):
        return JiraIssue(key=key, summary="Bug", url=f"https://acme.atlassian.net/browse/{key}")


class _FakeConfluence:
    def get_space(self, key):
        return ConfluenceSpace(id="7", key=key, name="Docs", url="https://acme.atlassian.net/wiki")

    def list_pages(self, space_id, limit):
        return [ConfluencePage(id="1", title="Setup", url="https://acme.atlassian.net/wiki/1")]

    def get_page(self, page_id):
        return ConfluencePage(id=page_id, title="Setup", url="https://acme.atlassian.net/wiki/1", body="Testo.")

    def search_pages(self, text, space_key, limit):
        return [ConfluenceSearchHit(id="1", title="Setup", url="https://acme.atlassian.net/wiki/1")]


def test_masking(api):
    entry = api.masking.add(PROJECT, "term", "Grandi Navi")

    assert (entry.alias, entry.manual) == ("TERMINE_1", True)
    assert [e.value for e in api.masking.entries(PROJECT)] == ["Grandi Navi"]
    api.masking.remove(PROJECT, entry.alias)
    assert api.masking.entries(PROJECT) == []


def test_admin(api, store_service):
    store_service.save_run(make_run_record("run 1"))

    assert api.admin.config().settings
    assert api.admin.runs()[0].run_id == "run 1"
    assert api.admin.trace("run 1")["input"] == "Saluta Mario"
    models = api.admin.models()
    assert api.admin.save_models(models) == models
