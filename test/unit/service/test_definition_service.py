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
from service.pipeline_service import PipelineService

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
        function: git_status
        params: {repository: ""}
      - name: Rivedi
        agent: reviewer
    edges:
      - {from: input, to: Stato}
      - {from: Stato, to: Rivedi, if: contains, value: modified}
"""


@pytest.fixture
def services(store_service, agent_config_service, worker_store, make_agent_service):
    store_service.save_definition("global-agent.yml", "")  # each test writes what it needs
    store_service.save_project(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    agents = make_agent_service()
    pipelines = PipelineService(store_service, agent_config_service, worker_store)
    chatbots = ChatbotService(store_service, agent_config_service, agents)
    return DefinitionService(store_service, agent_config_service, chatbots, pipelines), chatbots, pipelines


def _write(store_service, path, text):
    store_service.save_definition(path, text)


def _outcomes(report):
    return [(item.file, item.name, item.outcome.value) for item in report.items]


# ---------------------------------------------------------------- agents

def test_a_project_agent_is_created_then_unchanged_then_updated_with_a_new_prompt_version(services, store_service, agent_config_service):
    definitions, _, _ = services
    _write(store_service, f"{PROJECT_DIR}/agent.yml", "agents:" + REVIEWER)

    assert _outcomes(definitions.sync("acme")) == [(f"{PROJECT_DIR}/agent.yml", "reviewer", "created")]
    assert _outcomes(definitions.sync("acme"))[0][2] == "unchanged"

    _write(store_service, f"{PROJECT_DIR}/agent.yml", "agents:" + REVIEWER.replace("Sei un revisore.", "Sei severo."))
    assert _outcomes(definitions.sync("acme"))[0][2] == "updated"

    agent = agent_config_service.get_config("reviewer")
    assert (agent.project_name, agent.role_name, agent.tool_names) == ("acme", "revisione", ["git_status"])
    assert [prompt.version for prompt in agent_config_service.list_prompts("revisione")] == [2, 1]
    assert agent.prompt_id == agent_config_service.latest_prompt("revisione").id


def test_global_agents_go_to_the_library_with_a_global_role(services, store_service, agent_config_service):
    definitions, _, _ = services
    _write(store_service, "global-agent.yml", "agents:" + REVIEWER.replace("reviewer", "globale").replace("revisione", "generale"))

    assert _outcomes(definitions.sync("acme")) == [("global-agent.yml", "globale", "created")]
    assert agent_config_service.get_config("globale").project_name is None
    assert agent_config_service.get_role("generale").project_name is None


def test_a_role_of_another_scope_is_an_error_and_the_other_agents_are_applied(services, store_service):
    definitions, _, _ = services
    other = REVIEWER.replace("reviewer", "secondo").replace("revisione", "altro")
    _write(store_service, f"{PROJECT_DIR}/agent.yml", "agents:" + REVIEWER.replace("role: revisione", "role: hello") + other)

    report = definitions.sync("acme")

    assert [(item.name, item.outcome.value) for item in report.items] == [("reviewer", "error"), ("secondo", "created")]
    assert "non è del progetto acme" in report.items[0].message


def test_at_startup_only_the_missing_global_agents_are_created(services, store_service, agent_config_service):
    definitions, _, _ = services
    agent_config_service.save_config(agent_config_service.get_config("hello").model_copy(update={"tool_names": []}))  # from UI
    hello = f"""
  - name: hello
    role: hello
    model: {MODEL}
    tools: [hello_world]
    system_prompt: Un altro prompt.
"""
    _write(store_service, "global-agent.yml", "agents:" + hello + REVIEWER.replace("reviewer", "nuovo").replace("revisione", "generale"))

    items = definitions.seed_global_agents()

    assert [(item.name, item.outcome.value) for item in items] == [("hello", "unchanged"), ("nuovo", "created")]
    assert agent_config_service.get_config("hello").tool_names == []  # the UI change stays
    assert agent_config_service.get_config("nuovo").project_name is None


def test_at_startup_a_broken_file_is_logged_not_raised(services, store_service, caplog):
    definitions, _, _ = services
    _write(store_service, "global-agent.yml", "agents: [rotto")

    [item] = definitions.seed_global_agents()

    assert item.outcome.value == "error" and "YAML non valido" in caplog.text


# --------------------------------------------------------------- chatbot

def test_the_project_chatbot_takes_its_prompt_from_a_file_next_to_it(services, store_service):
    definitions, chatbots, _ = services
    existing = chatbots.create_chatbot("acme", "assistente", "Prompt da UI.", MODEL)
    other = chatbots.create_chatbot("acme", "Vecchio", "Resta com'è.", MODEL)
    _write(store_service, f"{PROJECT_DIR}/prompt.md", "Sei il mio assistente.\n")
    _write(store_service, f"{PROJECT_DIR}/chat-bot.yml", f"""
name: Assistente
model: {MODEL}
tools: [list_automations, run_automation]
system_prompt_file: prompt.md
""")

    assert _outcomes(definitions.sync("acme")) == [(f"{PROJECT_DIR}/chat-bot.yml", "Assistente", "updated")]

    by_id = {bot.id: bot for bot in chatbots.list_chatbots("acme")}
    assert (by_id[existing.id].name, by_id[existing.id].system_prompt, by_id[existing.id].tool_names) == (
        "Assistente", "Sei il mio assistente.", ["list_automations", "run_automation"],
    )  # matched by name (case aside), not by being the only one
    assert by_id[other.id].system_prompt == "Resta com'è."  # not in the files: left alone


def test_a_project_has_many_chatbots_and_gets_the_global_ones_it_does_not_redefine(services, store_service):
    definitions, chatbots, _ = services
    _write(store_service, f"{PROJECT_DIR}/chat-bots.yml", f"""chatbots:
  - {{name: Automazioni, model: {MODEL}, system_prompt: Lancia automation.}}
  - {{name: Codice, model: {MODEL}, system_prompt: Delega a Copilot.}}
""")
    _write(store_service, "global-chat-bots.yml", f"""chatbots:
  - {{name: automazioni, model: {MODEL}, system_prompt: Sostituito dal progetto.}}
  - {{name: Generico, model: {MODEL}, system_prompt: Per tutti.}}
""")
    _write(store_service, "global-chat-bot.yml", f"name: Vecchio formato\nmodel: {MODEL}\nsystem_prompt: Ancora letto.\n")

    assert _outcomes(definitions.sync("acme")) == [
        (f"{PROJECT_DIR}/chat-bots.yml", "Automazioni", "created"), (f"{PROJECT_DIR}/chat-bots.yml", "Codice", "created"),
        ("global-chat-bots.yml", "Generico", "created"), ("global-chat-bot.yml", "Vecchio formato", "created"),
    ]
    assert sorted((bot.name, bot.system_prompt) for bot in chatbots.list_chatbots("acme")) == [
        ("Automazioni", "Lancia automation."), ("Codice", "Delega a Copilot."), ("Generico", "Per tutti."), ("Vecchio formato", "Ancora letto."),
    ]
    assert [entry.state.value for entry in definitions.preview("acme")] == ["exists"] * 4


def test_without_its_own_the_project_gets_the_global_chatbot(services, store_service):
    definitions, chatbots, _ = services
    _write(store_service, "global-chat-bot.yml", f"name: Globale\nmodel: {MODEL}\nsystem_prompt: Sei generico.\n")

    assert _outcomes(definitions.sync("acme")) == [("global-chat-bot.yml", "Globale", "created")]
    assert [bot.name for bot in chatbots.list_chatbots("acme")] == ["Globale"]


# ----------------------------------------------------------- automations

def test_an_automation_uses_the_agents_just_synced_and_keeps_its_graph_layout(services, store_service):
    definitions, _, pipelines = services
    _write(store_service, f"{PROJECT_DIR}/agent.yml", "agents:" + REVIEWER)
    _write(store_service, f"{PROJECT_DIR}/automation.yml", "automations:" + CONTROLLO)

    assert [outcome for _, _, outcome in _outcomes(definitions.sync("acme"))] == ["created", "created"]
    [automation] = pipelines.list_pipelines("acme")
    assert [(step.name, step.kind.value) for step in automation.steps] == [("Stato", "function"), ("Rivedi", "agent_config")]
    assert [(e.source, e.target, e.condition.value, e.value) for e in automation.edges] == [
        ("input", "Stato", "always", ""), ("Stato", "Rivedi", "contains", "modified"),
    ]
    assert _outcomes(definitions.sync("acme"))[-1][2] == "unchanged"

    moved = [step.model_copy(update={"position_x": 300.0}) for step in automation.steps]  # dragged in the editor
    pipelines.update_pipeline(automation.id, name="Controllo", description="Stato e revisione", steps=moved, edges=automation.edges)
    _write(store_service, f"{PROJECT_DIR}/automation.yml", "automations:" + CONTROLLO.replace("Stato e revisione", "Nuova"))

    assert _outcomes(definitions.sync("acme"))[-1][2] == "updated"
    [updated] = pipelines.list_pipelines("acme")
    assert updated.description == "Nuova"
    assert [(step.id, step.position_x) for step in updated.steps] == [(step.id, 300.0) for step in automation.steps]


def test_global_automations_are_added_unless_the_project_redefines_them(services, store_service):
    definitions, _, pipelines = services
    _write(store_service, "global-automation.yml", """automations:
  - {name: Stato, steps: [{name: S, function: git_status}]}
  - {name: Note, steps: [{name: N, function: save_note}]}
""")
    _write(store_service, f"{PROJECT_DIR}/automation.yml", """automations:
  - {name: stato, description: del progetto, steps: [{name: S, function: git_status}]}
""")

    assert _outcomes(definitions.sync("acme")) == [
        (f"{PROJECT_DIR}/automation.yml", "stato", "created"), ("global-automation.yml", "Note", "created"),
    ]
    assert sorted((p.name, p.description) for p in pipelines.list_pipelines("acme")) == [("Note", ""), ("stato", "del progetto")]


# ------------------------------------------------------------- the files

@pytest.mark.parametrize("text, message", [
    ("agents: [rotto", "YAML non valido"),
    ("- solo\n- una lista", "deve contenere dei campi"),
    ("agenti: []", "lista «agents:»"),
])
def test_a_broken_file_is_one_error_and_the_other_files_are_applied(services, store_service, text, message):
    definitions, _, pipelines = services
    _write(store_service, f"{PROJECT_DIR}/agent.yml", text)
    _write(store_service, f"{PROJECT_DIR}/automation.yml", "automations:\n  - {name: Semplice, steps: [{name: S, function: git_status}]}\n")

    report = definitions.sync("acme")

    assert [(item.file, item.outcome.value) for item in report.items] == [
        (f"{PROJECT_DIR}/agent.yml", "error"), (f"{PROJECT_DIR}/automation.yml", "created"),
    ]
    assert message in report.items[0].message
    assert [p.name for p in pipelines.list_pipelines("acme")] == ["Semplice"]


@pytest.mark.parametrize("element, message", [
    (REVIEWER + "    colore: rosso\n", "colore"),  # a typo is never ignored
    (REVIEWER.replace(f"model: {MODEL}", "model: nessuno"), "model"),
])
def test_a_broken_element_is_reported_with_its_name(services, store_service, element, message):
    definitions, _, _ = services
    _write(store_service, f"{PROJECT_DIR}/agent.yml", "agents:" + element)

    [item] = definitions.sync("acme").items

    assert (item.name, item.outcome.value) == ("reviewer", "error") and message in item.message


def test_steps_must_be_one_kind(services, store_service):
    definitions, _, _ = services
    _write(store_service, f"{PROJECT_DIR}/automation.yml",
           "automations:\n  - {name: Doppio, steps: [{name: X, function: git_status, agent: reviewer}]}\n")

    [item] = definitions.sync("acme").items

    assert item.outcome.value == "error" and "uno solo tra function, agent e system_prompt" in item.message


def test_missing_or_empty_files_define_nothing_and_an_unknown_project(services, store_service):
    definitions, _, _ = services
    _write(store_service, "global-agent.yml", "# agenti della Libreria: niente per ora\n")

    assert definitions.sync("acme").items == []
    with pytest.raises(NotFoundError):
        definitions.sync("missing")


# --------------------------------------------------------- preview, choice

def test_the_preview_lists_what_the_files_define_and_applies_nothing(services, store_service):
    definitions, chatbots, pipelines = services
    _write(store_service, f"{PROJECT_DIR}/agent.yml", "agents:" + REVIEWER + "  - {name: rotto}\n")
    _write(store_service, f"{PROJECT_DIR}/automation.yml", "automations:" + CONTROLLO)
    _write(store_service, "global-chat-bot.yml", f"name: Assistente\nmodel: {MODEL}\nsystem_prompt: Ciao.\n")
    _write(store_service, "global-automation.yml", "automations: [rotto")
    definitions.sync("acme", only=[DefinitionKey(kind=DefinitionKind.AGENT, file=f"{PROJECT_DIR}/agent.yml", name="reviewer")])

    preview = [(entry.kind.value, entry.file, entry.name, entry.state.value) for entry in definitions.preview("acme")]

    assert preview == [
        ("agent", f"{PROJECT_DIR}/agent.yml", "reviewer", "exists"),
        ("agent", f"{PROJECT_DIR}/agent.yml", "rotto", "error"),
        ("chatbot", "global-chat-bot.yml", "Assistente", "new"),
        ("automation", f"{PROJECT_DIR}/automation.yml", "Controllo", "new"),
        ("automation", "global-automation.yml", None, "error"),
    ]
    assert "YAML non valido" in definitions.preview("acme")[-1].message
    assert chatbots.list_chatbots("acme") == [] and pipelines.list_pipelines("acme") == []  # nothing applied


def test_a_sync_can_apply_only_the_chosen_elements(services, store_service):
    definitions, chatbots, pipelines = services
    _write(store_service, f"{PROJECT_DIR}/agent.yml", "agents:" + REVIEWER)
    _write(store_service, f"{PROJECT_DIR}/automation.yml", "automations:" + CONTROLLO + "  - {name: Altra, steps: [{name: S, function: git_status}]}\n")
    _write(store_service, "global-chat-bot.yml", f"name: Assistente\nmodel: {MODEL}\nsystem_prompt: Ciao.\n")
    chosen = [entry for entry in definitions.preview("acme") if entry.name in {"reviewer", "Controllo"}]

    report = definitions.sync("acme", only=chosen)

    assert _outcomes(report) == [(f"{PROJECT_DIR}/agent.yml", "reviewer", "created"), (f"{PROJECT_DIR}/automation.yml", "Controllo", "created")]
    assert [p.name for p in pipelines.list_pipelines("acme")] == ["Controllo"] and chatbots.list_chatbots("acme") == []
    assert definitions.sync("acme", only=[]).items == []


def test_an_automation_chatbot_from_the_files_gets_its_fixed_tools(services, store_service):
    definitions, chatbots, _ = services
    _write(store_service, f"{PROJECT_DIR}/chat-bots.yml", f"""chatbots:
  - {{name: Automazioni, kind: automation, model: {MODEL}, system_prompt: Lancia automation.}}
  - {{name: Sbagliato, kind: automation, model: {MODEL}, tools: [git_status], system_prompt: X.}}
""")

    assert _outcomes(definitions.sync("acme")) == [
        (f"{PROJECT_DIR}/chat-bots.yml", "Automazioni", "created"), (f"{PROJECT_DIR}/chat-bots.yml", "Sbagliato", "error"),
    ]
    [bot] = chatbots.list_chatbots("acme")
    assert (bot.kind.value, bot.tool_names) == ("automation", ["list_automations", "run_automation", "automation_status"])
    assert _outcomes(definitions.sync("acme"))[0] == (f"{PROJECT_DIR}/chat-bots.yml", "Automazioni", "unchanged")
    assert "togli tools" in definitions.preview("acme")[1].message


def test_the_default_chatbots_are_created_where_missing_and_never_changed(services, store_service, caplog):
    definitions, chatbots, _ = services
    mine = chatbots.create_chatbot("acme", "segretario", system_prompt="Mio.", model=MODEL)  # same name: left as it is

    assert definitions.seed_default_chatbots(["acme"]) == 1
    bots = {bot.name: bot for bot in chatbots.list_chatbots("acme")}
    assert set(bots) == {"Chat bot", "segretario"}
    assert bots["Chat bot"].kind.value == "automation" and bots["Chat bot"].tool_names == ["list_automations", "run_automation", "automation_status"]
    assert bots["segretario"] == mine
    assert definitions.seed_default_chatbots(["acme"]) == 0  # already there

    store_service.save_project(Project(name="beta", source=ProjectSource.FOLDER, root_path="/code/beta"))
    default_model = store_service.get_chat_model("openrouter/google/gemini-3.1-flash-lite-preview")
    store_service.save_chat_model(default_model.model_copy(update={"active": False}))

    assert definitions.seed_default_chatbots(["beta"]) == 0  # logged, not raised: the app starts anyway
    assert chatbots.list_chatbots("beta") == [] and "è disattivato" in caplog.text
