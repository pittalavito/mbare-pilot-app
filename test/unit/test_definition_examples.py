"""The example definitions (resource/definition-example/) stay valid with the
same rules the app applies, and copying them never overwrites the user's files."""
import yaml

from domain.project import coding_agent
from domain.project.definition_examples import EXAMPLES_DIR, copy_missing
from function.registry import get_function
from models.domain.definitions import AgentFile, AutomationFile, ChatbotFile
from service.store_service import StoreService


def _yaml(name: str) -> dict:
    return yaml.safe_load((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def test_the_examples_are_valid_definitions(config, engine, redis_client):
    for agent in _yaml("global-agent.yml")["agents"]:
        AgentFile.model_validate(agent)
    for chatbot in _yaml("global-chat-bots.yml")["chatbots"]:
        ChatbotFile.model_validate(chatbot)
    for automation in _yaml("global-automation.yml")["automations"]:
        for step in AutomationFile.model_validate(automation).steps:
            if step.function:
                get_function(step.function).validate_params(step.params)

    for path in config.definitions_root.iterdir():  # the tests' own definitions out of the way
        path.unlink()
    assert copy_missing(config.definitions_root)
    settings = coding_agent.load(StoreService(engine=engine, redis_client=redis_client))
    assert settings.denied_tools and "bugfix" in settings.prompts
    assert all(model.price for model in settings.models if model.name not in {"auto", "gpt-5.5"})


def test_copying_the_examples_never_overwrites(tmp_path):
    target = tmp_path / "definition"
    (target / "coding-agent").mkdir(parents=True)
    (target / "global-coding-agent.yml").write_text("il mio", encoding="utf-8")

    copied = copy_missing(target)

    assert "global-coding-agent.yml" not in copied and (target / "global-coding-agent.yml").read_text(encoding="utf-8") == "il mio"
    assert copied == ["coding-agent/bugfix.md", "global-agent.yml", "global-automation.yml", "global-chat-bots.yml"]
    assert not (target / "README.md").exists()
    assert copy_missing(target) == []
