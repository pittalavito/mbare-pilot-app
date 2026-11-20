"""Definitions as files under definition/: global agents (Library), the
project's agents, its chatbot (or the global one) and its automations (plus the
global ones it does not redefine), applied by sync. The file wins over the UI,
matched by name; a broken element is reported and the others applied."""
import pytest

from core.error import NotFoundError
from models.domain.definitions import DefinitionKey, DefinitionKind
from models.domain.project import Project, ProjectSource
from service.chatbot_service import ChatbotService
from service.definition_service import DefinitionService

ARCHITECT_TOOLS = ["list_tools", "list_agents", "list_automations", "read_automation", "validate_automation", "request_tool", "search_context"]

MODEL = "openai/gpt-4o"
PROJECT_DIR = "project/acme"

REVIEWER = f"""
  - name: reviewer
    description: Rivede il codice
    role: revisione
    model: {MODEL}
    tools: [git_status]
    system_prompt: |
      Sei un revisore.
"""

CONTROLLO = """
  - name: Controllo
    description: Stato e revisione
    steps:
      - name: Stato
        tool: git_status
        args: {repository: ""}
      - name: Rivedi
        agent: reviewer
    edges:
      - {from: input, to: Stato}
      - {from: Stato, to: Rivedi, if: contains, value: modified}
"""


@pytest.fixture
def services(agent_config_service, make_agent_service, catalog_store, pipeline_service, agent_store, project_store, chatbot_store, definition_store):
    definition_store.save_definition("agents/agents.yml", "")  # each test writes what it needs
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    agents = make_agent_service()
    pipelines = pipeline_service
    chatbots = ChatbotService(chatbot_store, project_store, catalog_store, agent_config_service, agents)
    return DefinitionService(definition_store, project_store, agent_store, agent_config_service, chatbots, pipelines), chatbots, pipelines


def _write(definition_store, path, text):
    definition_store.save_definition(path, text)


def _outcomes(report):
    return [(item.file, item.name, item.outcome.value) for item in report.items]


# ---------------------------------------------------------------- agents

def test_a_project_agent_is_created_then_unchanged_then_updated_with_a_new_prompt_version(services, definition_store, agent_config_service):
    definitions, _, _ = services
    _write(definition_store, f"{PROJECT_DIR}/agents/agents.yml", "agents:" + REVIEWER)

    assert _outcomes(definitions.sync("acme")) == [(f"{PROJECT_DIR}/agents/agents.yml", "reviewer", "created")]
    assert _outcomes(definitions.sync("acme"))[0][2] == "unchanged"

    _write(definition_store, f"{PROJECT_DIR}/agents/agents.yml", "agents:" + REVIEWER.replace("Sei un revisore.", "Sei severo."))
    assert _outcomes(definitions.sync("acme"))[0][2] == "updated"

    agent = agent_config_service.get_config("reviewer")
    assert (agent.project_name, agent.role_name, agent.tool_names) == ("acme", "revisione", ["git_status"])
    assert [prompt.version for prompt in agent_config_service.list_prompts("revisione")] == [2, 1]
    assert agent.prompt_id == agent_config_service.latest_prompt("revisione").id


def test_global_agents_go_to_the_library_with_a_global_role(services, definition_store, agent_config_service):
    definitions, _, _ = services
    _write(definition_store, "agents/agents.yml", "agents:" + REVIEWER.replace("reviewer", "globale").replace("revisione", "generale"))

    assert _outcomes(definitions.sync("acme")) == [("agents/agents.yml", "globale", "created")]
    assert agent_config_service.get_config("globale").project_name is None
    assert agent_config_service.get_role("generale").project_name is None


def test_a_role_of_another_scope_is_an_error_and_the_other_agents_are_applied(services, definition_store):
    definitions, _, _ = services
    other = REVIEWER.replace("reviewer", "secondo").replace("revisione", "altro")
    _write(definition_store, f"{PROJECT_DIR}/agents/agents.yml", "agents:" + REVIEWER.replace("role: revisione", "role: hello") + other)

    report = definitions.sync("acme")

    assert [(item.name, item.outcome.value) for item in report.items] == [("reviewer", "error"), ("secondo", "created")]
    assert "non è del progetto acme" in report.items[0].message


def test_at_startup_every_file_is_applied(services, definition_store, agent_config_service):
    """The defaults follow the files (a change made only from the UI goes back to the file)."""
    definitions, _, _ = services
    agent_config_service.save_config(agent_config_service.get_config("hello").model_copy(update={"tool_names": []}))  # from UI
    hello = f"""
  - name: hello
    role: hello
    model: {MODEL}
    tools: [hello_world]
    system_prompt: Un altro prompt.
"""
    _write(definition_store, "agents/agents.yml", "agents:" + hello + REVIEWER.replace("reviewer", "nuovo").replace("revisione", "generale"))

    items = definitions.sync_at_startup([])

    assert [(item.name, item.outcome.value) for item in items] == [("hello", "updated"), ("nuovo", "created")]
    assert agent_config_service.get_config("hello").tool_names == ["hello_world"]
    assert agent_config_service.get_config("nuovo").project_name is None


def test_at_startup_a_broken_file_is_logged_not_raised(services, definition_store, caplog):
    definitions, _, _ = services
    _write(definition_store, "agents/agents.yml", "agents: [rotto")

    [item] = definitions.sync_at_startup(["acme", "nessuno"])

    assert item.outcome.value == "error" and "YAML non valido" in caplog.text and "Progetto non trovato: nessuno" in caplog.text


def test_at_startup_the_files_of_the_old_layout_are_reported_not_read(services, definition_store, caplog):
    definitions, _, _ = services
    _write(definition_store, "global-agent.yml", "agents:" + REVIEWER)
    _write(definition_store, "coding-agent/bug.md", "Il bug: {task}")
    _write(definition_store, f"{PROJECT_DIR}/chat-bots.yml", "chatbots: []\n")
    _write(definition_store, f"{PROJECT_DIR}/agents/agents.yml", "")  # the new layout: not reported

    assert definitions.legacy_files(["acme"]) == ["global-agent.yml", "coding-agent", f"{PROJECT_DIR}/chat-bots.yml"]
    assert definitions.sync_at_startup(["acme"]) == []  # nothing of the old files is applied
    assert "definition/global-agent.yml: nome della struttura vecchia" in caplog.text
    assert f"definition/{PROJECT_DIR}/chat-bots.yml" in caplog.text


# --------------------------------------------------------------- chatbot

def test_the_project_chatbot_takes_its_prompt_from_a_file_next_to_it(services, definition_store):
    definitions, chatbots, _ = services
    existing = chatbots.create_chatbot("acme", "assistente", "Prompt da UI.", MODEL)
    other = chatbots.create_chatbot("acme", "Vecchio", "Resta com'è.", MODEL)
    _write(definition_store, f"{PROJECT_DIR}/agents/prompt.md", "Sei il mio assistente.\n")
    _write(definition_store, f"{PROJECT_DIR}/agents/chatbots.yml", f"""chatbots:
  - name: Assistente
    model: {MODEL}
    tools: [list_automations, run_automation]
    system_prompt_file: prompt.md
""")

    assert _outcomes(definitions.sync("acme")) == [(f"{PROJECT_DIR}/agents/chatbots.yml", "Assistente", "updated")]

    by_id = {bot.id: bot for bot in chatbots.list_chatbots("acme")}
    assert (by_id[existing.id].name, by_id[existing.id].system_prompt, by_id[existing.id].tool_names) == (
        "Assistente", "Sei il mio assistente.", ["list_automations", "run_automation"],
    )  # matched by name (case aside), not by being the only one
    assert by_id[other.id].system_prompt == "Resta com'è."  # not in the files: left alone


def test_a_project_has_many_chatbots_and_gets_the_global_ones_it_does_not_redefine(services, definition_store):
    definitions, chatbots, _ = services
    _write(definition_store, f"{PROJECT_DIR}/agents/chatbots.yml", f"""chatbots:
  - {{name: Automazioni, model: {MODEL}, system_prompt: Lancia automation.}}
  - {{name: Codice, model: {MODEL}, system_prompt: Delega a Copilot.}}
""")
    _write(definition_store, "agents/chatbots.yml", f"""chatbots:
  - {{name: automazioni, model: {MODEL}, system_prompt: Sostituito dal progetto.}}
  - {{name: Generico, model: {MODEL}, system_prompt: Per tutti.}}
""")

    assert _outcomes(definitions.sync("acme")) == [
        (f"{PROJECT_DIR}/agents/chatbots.yml", "Automazioni", "created"), (f"{PROJECT_DIR}/agents/chatbots.yml", "Codice", "created"),
        ("agents/chatbots.yml", "Generico", "created"),
    ]
    assert sorted((bot.name, bot.system_prompt) for bot in chatbots.list_chatbots("acme")) == [
        ("Automazioni", "Lancia automation."), ("Codice", "Delega a Copilot."), ("Generico", "Per tutti."),
    ]
    assert [entry.state.value for entry in definitions.preview("acme")] == ["exists"] * 3


def test_without_its_own_the_project_gets_the_global_chatbot(services, definition_store):
    definitions, chatbots, _ = services
    _write(definition_store, "agents/chatbots.yml", f"chatbots:\n  - {{name: Globale, model: {MODEL}, system_prompt: Sei generico.}}\n")

    assert _outcomes(definitions.sync("acme")) == [("agents/chatbots.yml", "Globale", "created")]
    assert [bot.name for bot in chatbots.list_chatbots("acme")] == ["Globale"]


# ----------------------------------------------------------- automations

def test_an_automation_uses_the_agents_just_synced_and_keeps_its_graph_layout(services, definition_store):
    definitions, _, pipelines = services
    _write(definition_store, f"{PROJECT_DIR}/agents/agents.yml", "agents:" + REVIEWER)
    _write(definition_store, f"{PROJECT_DIR}/automations/automations.yml", "automations:" + CONTROLLO)

    assert [outcome for _, _, outcome in _outcomes(definitions.sync("acme"))] == ["created", "created"]
    [automation] = pipelines.list_pipelines("acme")
    assert [(step.name, step.kind.value) for step in automation.steps] == [("Stato", "tool"), ("Rivedi", "agent_config")]
    assert [(e.source, e.target, e.condition.value, e.value) for e in automation.edges] == [
        ("input", "Stato", "always", ""), ("Stato", "Rivedi", "contains", "modified"),
    ]
    assert _outcomes(definitions.sync("acme"))[-1][2] == "unchanged"

    moved = [step.model_copy(update={"position_x": 300.0}) for step in automation.steps]  # dragged in the editor
    pipelines.update_pipeline(automation.id, name="Controllo", description="Stato e revisione", steps=moved, edges=automation.edges)
    _write(definition_store, f"{PROJECT_DIR}/automations/automations.yml", "automations:" + CONTROLLO.replace("Stato e revisione", "Nuova"))

    assert _outcomes(definitions.sync("acme"))[-1][2] == "updated"
    [updated] = pipelines.list_pipelines("acme")
    assert updated.description == "Nuova"
    assert [(step.id, step.position_x) for step in updated.steps] == [(step.id, 300.0) for step in automation.steps]


def test_global_automations_are_added_unless_the_project_redefines_them(services, definition_store):
    definitions, _, pipelines = services
    _write(definition_store, "automations/automations.yml", """automations:
  - {name: Stato, steps: [{name: S, tool: git_status, args: {repository: "*"}}]}
  - {name: Note, steps: [{name: N, tool: save_note, args: {content: "{input}"}}]}
""")
    _write(definition_store, f"{PROJECT_DIR}/automations/automations.yml", """automations:
  - {name: stato, description: del progetto, steps: [{name: S, tool: git_status, args: {repository: "*"}}]}
""")

    assert _outcomes(definitions.sync("acme")) == [
        (f"{PROJECT_DIR}/automations/automations.yml", "stato", "created"), ("automations/automations.yml", "Note", "created"),
    ]
    assert sorted((p.name, p.description) for p in pipelines.list_pipelines("acme")) == [("Note", ""), ("stato", "del progetto")]


# ------------------------------------------------------------- the files

@pytest.mark.parametrize("text, message", [
    ("agents: [rotto", "YAML non valido"),
    ("- solo\n- una lista", "deve contenere dei campi"),
    ("agenti: []", "lista «agents:»"),
])
def test_a_broken_file_is_one_error_and_the_other_files_are_applied(services, definition_store, text, message):
    definitions, _, pipelines = services
    _write(definition_store, f"{PROJECT_DIR}/agents/agents.yml", text)
    _write(definition_store, f"{PROJECT_DIR}/automations/automations.yml",
           "automations:\n  - {name: Semplice, steps: [{name: S, tool: git_status, args: {repository: api}}]}\n")

    report = definitions.sync("acme")

    assert [(item.file, item.outcome.value) for item in report.items] == [
        (f"{PROJECT_DIR}/agents/agents.yml", "error"), (f"{PROJECT_DIR}/automations/automations.yml", "created"),
    ]
    assert message in report.items[0].message
    assert [p.name for p in pipelines.list_pipelines("acme")] == ["Semplice"]


@pytest.mark.parametrize("element, message", [
    (REVIEWER + "    colore: rosso\n", "colore"),  # a typo is never ignored
    (REVIEWER.replace(f"model: {MODEL}", "model: nessuno"), "model"),
])
def test_a_broken_element_is_reported_with_its_name(services, definition_store, element, message):
    definitions, _, _ = services
    _write(definition_store, f"{PROJECT_DIR}/agents/agents.yml", "agents:" + element)

    [item] = definitions.sync("acme").items

    assert (item.name, item.outcome.value) == ("reviewer", "error") and message in item.message


def test_steps_must_be_one_kind(services, definition_store):
    definitions, _, _ = services
    _write(definition_store, f"{PROJECT_DIR}/automations/automations.yml",
           "automations:\n  - {name: Doppio, steps: [{name: X, tool: git_status, agent: reviewer}]}\n")

    [item] = definitions.sync("acme").items

    assert item.outcome.value == "error" and "uno solo tra tool, agent e system_prompt" in item.message


def test_missing_or_empty_files_define_nothing_and_an_unknown_project(services, definition_store):
    definitions, _, _ = services
    _write(definition_store, "agents/agents.yml", "# agenti della Libreria: niente per ora\n")

    assert definitions.sync("acme").items == []
    with pytest.raises(NotFoundError):
        definitions.sync("missing")


# --------------------------------------------------------- preview, choice

def test_the_preview_lists_what_the_files_define_and_applies_nothing(services, definition_store):
    definitions, chatbots, pipelines = services
    _write(definition_store, f"{PROJECT_DIR}/agents/agents.yml", "agents:" + REVIEWER + "  - {name: rotto}\n")
    _write(definition_store, f"{PROJECT_DIR}/automations/automations.yml", "automations:" + CONTROLLO)
    _write(definition_store, "agents/chatbots.yml", f"chatbots:\n  - {{name: Assistente, model: {MODEL}, system_prompt: Ciao.}}\n")
    _write(definition_store, "automations/automations.yml", "automations: [rotto")
    definitions.sync("acme", only=[DefinitionKey(kind=DefinitionKind.AGENT, file=f"{PROJECT_DIR}/agents/agents.yml", name="reviewer")])

    preview = [(entry.kind.value, entry.file, entry.name, entry.state.value) for entry in definitions.preview("acme")]

    assert preview == [
        ("agent", f"{PROJECT_DIR}/agents/agents.yml", "reviewer", "exists"),
        ("agent", f"{PROJECT_DIR}/agents/agents.yml", "rotto", "error"),
        ("chatbot", "agents/chatbots.yml", "Assistente", "new"),
        ("automation", f"{PROJECT_DIR}/automations/automations.yml", "Controllo", "new"),
        ("automation", "automations/automations.yml", None, "error"),
    ]
    assert "YAML non valido" in definitions.preview("acme")[-1].message
    assert chatbots.list_chatbots("acme") == [] and pipelines.list_pipelines("acme") == []  # nothing applied


def test_a_sync_can_apply_only_the_chosen_elements(services, definition_store):
    definitions, chatbots, pipelines = services
    _write(definition_store, f"{PROJECT_DIR}/agents/agents.yml", "agents:" + REVIEWER)
    _write(definition_store, f"{PROJECT_DIR}/automations/automations.yml",
           "automations:" + CONTROLLO + "  - {name: Altra, steps: [{name: S, tool: git_status}]}\n")
    _write(definition_store, "agents/chatbots.yml", f"chatbots:\n  - {{name: Assistente, model: {MODEL}, system_prompt: Ciao.}}\n")
    chosen = [entry for entry in definitions.preview("acme") if entry.name in {"reviewer", "Controllo"}]

    report = definitions.sync("acme", only=chosen)

    assert _outcomes(report) == [(f"{PROJECT_DIR}/agents/agents.yml", "reviewer", "created"),
                                 (f"{PROJECT_DIR}/automations/automations.yml", "Controllo", "created")]
    assert [p.name for p in pipelines.list_pipelines("acme")] == ["Controllo"] and chatbots.list_chatbots("acme") == []
    assert definitions.sync("acme", only=[]).items == []


def test_a_chatbot_s_tools_come_from_the_files_and_must_suit_its_kind(services, definition_store):
    definitions, chatbots, _ = services
    _write(definition_store, f"{PROJECT_DIR}/agents/chatbots.yml", f"""chatbots:
  - {{name: Automazioni, kind: automation, model: {MODEL}, tools: [list_tools, validate_automation], system_prompt: X.}}
  - {{name: Sbagliato, kind: automation, model: {MODEL}, tools: [git_status], system_prompt: X.}}
""")

    assert _outcomes(definitions.sync("acme")) == [
        (f"{PROJECT_DIR}/agents/chatbots.yml", "Automazioni", "created"), (f"{PROJECT_DIR}/agents/chatbots.yml", "Sbagliato", "error"),
    ]
    [bot] = chatbots.list_chatbots("acme")
    assert (bot.kind.value, bot.tool_names) == ("automation", ["list_tools", "validate_automation"])  # as written, not imposed
    assert _outcomes(definitions.sync("acme"))[0] == (f"{PROJECT_DIR}/agents/chatbots.yml", "Automazioni", "unchanged")
    assert "non può usare git_status" in definitions.preview("acme")[1].message


def test_the_chatbots_of_the_files_are_created_or_updated_and_the_ui_ones_left_alone(services, caplog, catalog_store, project_store,
                                                                                   default_chatbots):
    definitions, chatbots, _ = services
    mine = chatbots.create_chatbot("acme", "Mio", system_prompt="Mio.", model=MODEL)  # created from the UI: never touched

    definitions.sync_at_startup(["acme"])
    bots = {bot.name: bot for bot in chatbots.list_chatbots("acme")}
    assert set(bots) == {"Architetto", "Dev", "Refiner", "Segretario", "Mio"}
    assert bots["Refiner"].kind.value == "refiner" and bots["Refiner"].tool_names == [
        "search_code", "read_agent_task", "update_agent_task", "finish_refinement", "search_context",
    ]
    assert bots["Architetto"].tool_names == ARCHITECT_TOOLS and bots["Architetto"].model == "openrouter/google/gemini-2.5-pro"
    assert bots["Mio"] == mine
    chatbots.update_chatbot(bots["Dev"].id, **{**bots["Dev"].model_dump(include={"name", "kind", "model", "description", "max_steps",
                                                                                  "tool_names"}), "system_prompt": "Cambiato."})
    definitions.sync_at_startup(["acme"])
    assert next(bot for bot in chatbots.list_chatbots("acme") if bot.name == "Dev").system_prompt != "Cambiato."  # the file wins

    project_store.save(Project(name="beta", source=ProjectSource.FOLDER, root_path="/code/beta"))
    for key in ("openrouter/google/gemini-3.1-flash-lite", "openrouter/google/gemini-2.5-pro"):  # the others' and the Architect's
        catalog_store.save_model(catalog_store.get_model(key).model_copy(update={"active": False}))
    definitions.sync_at_startup(["beta"])  # logged, not raised: the app starts anyway
    assert chatbots.list_chatbots("beta") == [] and "è disattivato" in caplog.text


def test_without_the_files_a_project_has_no_chatbots_and_a_broken_file_is_logged(services, caplog, definition_store):
    definitions, chatbots, _ = services
    definitions.sync_at_startup(["acme"])
    assert chatbots.list_chatbots("acme") == []
    _write(definition_store, "agents/chatbots.yml", "chatbots: [\n")
    definitions.sync_at_startup(["acme"])
    assert "YAML non valido" in caplog.text


# ------------------------------------------------------------- layers

APP_BOTS = f"""chatbots:
  - name: Refiner
    kind: refiner
    model: {MODEL}
    tools: [read_agent_task]
    system_prompt: Prompt dell'app.
  - name: Dev
    kind: operator
    model: {MODEL}
    tools: [git_status]
    system_prompt: Dev dell'app.
"""


@pytest.fixture
def layered(services, tmp_path, project_store, agent_store, agent_config_service, config):
    from service.store.definition_store import DefinitionStore
    _, chatbots, pipelines = services
    app = tmp_path / "app-definitions"
    (app / "agents").mkdir(parents=True)
    (app / "agents/chatbots.yml").write_text(APP_BOTS, encoding="utf-8")
    store = DefinitionStore(config.definitions_root, app)
    return DefinitionService(store, project_store, agent_store, agent_config_service, chatbots, pipelines), chatbots, store


def test_the_data_folder_wins_by_name_and_says_where_each_comes_from(layered):
    definitions, chatbots, store = layered
    store.save_definition("agents/chatbots.yml", f"chatbots:\n  - name: refiner\n    kind: refiner\n    model: {MODEL}\n"
                                                  f"    tools: [read_agent_task]\n    system_prompt: Il mio prompt.\n"
                                                  f"  - name: Nuovo\n    model: {MODEL}\n    system_prompt: Mio nuovo.\n")
    definitions.sync_at_startup(["acme"])

    bots = {bot.name.lower(): bot for bot in chatbots.list_chatbots("acme")}
    assert bots["refiner"].system_prompt == "Il mio prompt." and bots["dev"].system_prompt == "Dev dell'app." and "nuovo" in bots
    origins = {entry.name.lower(): entry.origin for entry in definitions.preview("acme") if entry.kind is DefinitionKind.CHATBOT}
    assert origins == {"refiner": "tuo", "dev": "app", "nuovo": "tuo"}
    assert definitions.chatbot_origin("acme", "Dev") == "app" and definitions.chatbot_origin("acme", "Altro") is None


def test_saving_a_default_from_the_ui_writes_the_data_folder_and_revert_brings_the_app_back(layered):
    definitions, chatbots, store = layered
    definitions.sync_at_startup(["acme"])
    dev = next(bot for bot in chatbots.list_chatbots("acme") if bot.name == "Dev")
    changed = chatbots.update_chatbot(dev.id, **{**dev.model_dump(include={"name", "kind", "model", "description", "max_steps",
                                                                            "tool_names"}), "system_prompt": "Dev mio."})

    assert definitions.save_chatbot("acme", changed) == "agents/chatbots.yml"
    assert "Dev mio." in store.read_layers("agents/chatbots.yml")[0] and definitions.chatbot_origin("acme", "Dev") == "tuo"
    definitions.sync_at_startup(["acme"])
    assert chatbots.get_chatbot(dev.id).system_prompt == "Dev mio."  # it stays after a restart
    mine = chatbots.create_chatbot("acme", "Solo UI", system_prompt="x", model=MODEL)
    assert definitions.save_chatbot("acme", mine) is None  # not a default: nothing written

    assert definitions.revert_chatbot("acme", "Dev").outcome.value == "updated"
    assert chatbots.get_chatbot(dev.id).system_prompt == "Dev dell'app." and store.origin("agents/chatbots.yml") == "app"
    with pytest.raises(NotFoundError):
        definitions.revert_chatbot("acme", "Solo UI")


def test_a_chatbot_of_the_project_file_is_saved_there(layered, config):
    definitions, chatbots, store = layered
    store.save_definition(f"{PROJECT_DIR}/agents/chatbots.yml", f"chatbots:\n  - name: Suo\n    model: {MODEL}\n    system_prompt: Del progetto.\n")
    store.save_definition("agents/chatbots.yml", "altro: 1\nchatbots: []\n")
    definitions.sync_at_startup(["acme"])
    suo = next(bot for bot in chatbots.list_chatbots("acme") if bot.name == "Suo")
    assert definitions.chatbot_origin("acme", "Suo") == "progetto"
    assert definitions.save_chatbot("acme", suo) == f"{PROJECT_DIR}/agents/chatbots.yml"
    dev = next(bot for bot in chatbots.list_chatbots("acme") if bot.name == "Dev")
    definitions.save_chatbot("acme", dev)
    definitions.revert_chatbot("acme", "Dev")
    assert store.read_layers("agents/chatbots.yml")[0].startswith("altro: 1")  # the rest of the user's file stays


def test_the_chatbot_api_says_the_origin_saves_back_and_reverts(stores, project_store, config, default_chatbots):
    from fastapi.testclient import TestClient

    from core.app import create_app
    from core.container import Container
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    with TestClient(create_app(Container(stores=stores))) as http:
        bots = {bot["name"]: bot for bot in http.get("/projects/acme/chatbots").json()}
        dev = bots["Dev"]
        assert dev["origin"] == "tuo"  # the tests' data folder holds the example files
        body = {key: dev[key] for key in ("name", "kind", "model", "description", "max_steps", "tool_names")} | {"system_prompt": "Mio."}
        assert http.put(f"/chatbots/{dev['id']}", json=body).json()["system_prompt"] == "Mio."
        assert "Mio." in (config.definitions_root / "agents/chatbots.yml").read_text(encoding="utf-8")
        assert http.post(f"/chatbots/{dev['id']}/revert").status_code == 404  # no app default in the tests
        mine = http.post("/projects/acme/chatbots", json={**body, "name": "Mio bot"}).json()
        assert mine["origin"] is None and http.patch(f"/chatbots/{mine['id']}/model", json={"model": dev["model"]}).json()["origin"] is None
