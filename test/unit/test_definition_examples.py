"""The app's default definitions (resource/definition/, plan 28) stay valid
with the same rules the app applies, and the data folder overrides them:
by name in the global YAML lists, by path for the other files."""
import yaml

from domain.project import coding_agent
from models.domain.definitions import AgentFile, AutomationFile, ChatbotFile
from service.store.definition_store import APP, USER, DefinitionStore
from tool.registry import TOOL_REGISTRY


def _yaml(config, name: str) -> dict:
    return yaml.safe_load((config.app_root / "resource" / "definition" / name).read_text(encoding="utf-8"))


def test_the_defaults_are_valid_definitions(config):
    for agent in _yaml(config, "global-agent.yml")["agents"]:
        AgentFile.model_validate(agent)
    for chatbot in _yaml(config, "global-chat-bots.yml")["chatbots"]:
        ChatbotFile.model_validate(chatbot)
    for automation in _yaml(config, "global-automation.yml")["automations"]:
        for step in AutomationFile.model_validate(automation).steps:
            if step.tool:
                properties, _ = TOOL_REGISTRY[step.tool].schema()
                assert set(step.args) <= set(properties), (automation["name"], step.name)

    for path in config.definitions_root.iterdir():  # the tests' own definitions out of the way
        path.unlink()
    store = DefinitionStore(config.definitions_root, config.app_root / "resource" / "definition")
    settings = coding_agent.load(store)
    assert settings.denied_tools and "bugfix" in settings.prompts
    assert all(model.price for model in settings.models if model.name not in {"auto", "gpt-5.5"})


def test_the_data_folder_wins_by_path_and_writes_go_there(tmp_path):
    app, mine = tmp_path / "app", tmp_path / "mine"
    (app / "context").mkdir(parents=True)
    (app / "context" / "a.md").write_text("app a", encoding="utf-8")
    (app / "context" / "b.md").write_text("app b", encoding="utf-8")
    store = DefinitionStore(mine, app)
    store.save_definition("context/b.md", "mio b")

    assert store.read_definition("context/a.md") == "app a" and store.read_definition("context/b.md") == "mio b"
    assert store.list_definitions("context") == ["context/a.md", "context/b.md"]
    assert (store.origin("context/a.md"), store.origin("context/b.md"), store.origin("context/c.md")) == (APP, USER, None)
    assert store.read_layers("context/b.md") == ("mio b", "app b")
    assert store.delete_definition("context/b.md") and store.read_definition("context/b.md") == "app b"
    assert not store.delete_definition("context/b.md")
    assert DefinitionStore(mine, tmp_path / "missing").read_definition("context/a.md") is None
