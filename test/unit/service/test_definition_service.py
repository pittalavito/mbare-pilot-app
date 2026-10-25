"""Definitions as files under definition/: global agents (Library), the
project's agents, its chatbot (or the global one) and its automations (plus the
global ones it does not redefine), applied by sync. The file wins over the UI,
matched by name; a broken element is reported and the others applied."""
import pytest

from core.error import NotFoundError
from models.domain.project import Project, ProjectSource
from service.agent_service import AgentService
from service.chat_service import ChatService
from service.chatbot_service import ChatbotService
from service.definition_service import DefinitionService
from service.git_service import GitService
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
def services(store_service, agent_config_service):
    store_service.save_project(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    agents = AgentService(ChatService(), agent_config_service, store_service, GitService(store_service))
    pipelines = PipelineService(store_service, agent_config_service)
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


# --------------------------------------------------------------- chatbot

def test_the_project_chatbot_takes_its_prompt_from_a_file_next_to_it(services, store_service):
    definitions, chatbots, _ = services
    existing = chatbots.create_chatbot("acme", "Vecchio", "Prompt da UI.", MODEL)
    _write(store_service, f"{PROJECT_DIR}/prompt.md", "Sei il mio assistente.\n")
    _write(store_service, f"{PROJECT_DIR}/chat-bot.yml", f"""
name: Assistente
model: {MODEL}
tools: [list_automations, run_automation]
system_prompt_file: prompt.md
""")
    _write(store_service, "global-chat-bot.yml", f"name: Globale\nmodel: {MODEL}\nsystem_prompt: Ignorato.\n")

    assert _outcomes(definitions.sync("acme")) == [(f"{PROJECT_DIR}/chat-bot.yml", "Assistente", "updated")]

    [chatbot] = chatbots.list_chatbots("acme")
    assert chatbot.id == existing.id  # one per project: renamed, not duplicated
    assert (chatbot.name, chatbot.system_prompt, chatbot.tool_names) == (
        "Assistente", "Sei il mio assistente.", ["list_automations", "run_automation"],
    )


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
