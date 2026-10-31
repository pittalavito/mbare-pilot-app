import pytest
from pydantic import ValidationError as PydanticValidationError

from core.error import ConflictError, NotFoundError, ValidationError
from fakes import FakeAgent
from models.domain.chatbot import MessageRole
from models.domain.project import Project, ProjectSource
from service import agent_service as agent_service_module
from service.chat_service import ChatService
from service.chatbot_service import ChatbotService

MODEL = "openai/gpt-4o"


class _Agents(list):
    """Every fake agent built in a test with the definition it was built from;
    set ``error`` to make the next ones fail."""
    error: Exception | None = None
    definitions: list


@pytest.fixture
def agents(monkeypatch):
    built = _Agents()
    built.definitions = []

    def create_agent(definition, client, tools):
        built.definitions.append((definition, [tool.name for tool in tools]))
        built.append(FakeAgent(built.error))
        return built[-1]

    monkeypatch.setattr(agent_service_module.AgentFactory, "create_agent", staticmethod(create_agent))
    return built


@pytest.fixture
def service(agent_config_service, agents, monkeypatch, make_agent_service, catalog_store, project_store, chatbot_store):
    for name in ("acme", "other"):
        project_store.save(Project(name=name, source=ProjectSource.FOLDER, root_path=f"/code/{name}"))
    chat = ChatService()
    monkeypatch.setattr(chat, "get_client", lambda model: object())
    agent_service = make_agent_service(chat)
    return ChatbotService(chatbot_store, project_store, catalog_store, agent_config_service, agent_service)


def _create(service, project="acme", name="Bot", **overrides):
    values = dict(system_prompt="Sei l'assistente del progetto.", model=MODEL)
    values.update(overrides)
    return service.create_chatbot(project, name, **values)


# ---------------------------------------------------------------- chatbots

def test_create_chatbot_with_its_own_agent(service):
    created = _create(
        service, name=" Supporto ", description=" Per i dev ", max_steps=6, tool_names=["git_status", "hello_world"],
    )

    assert created.id is not None
    assert (created.name, created.description) == ("Supporto", "Per i dev")
    assert (created.system_prompt, created.prompt_version, created.model) == ("Sei l'assistente del progetto.", 1, MODEL)
    assert (created.max_steps, created.tool_names) == (6, ["git_status", "hello_world"])
    assert [chatbot.name for chatbot in service.list_chatbots("acme")] == ["Supporto"]
    assert service.list_chatbots("other") == []


def test_available_tools_are_the_implemented_ones(service):
    assert {"git_status", "hello_world"} <= {tool.name for tool in service.available_tools()}


def test_unknown_tool_rejected(service):
    with pytest.raises(ValidationError, match="missing"):
        _create(service, tool_names=["git_status", "missing"])


@pytest.mark.parametrize("overrides", [dict(system_prompt="  "), dict(max_steps=0), dict(model="not/a-model")])
def test_invalid_agent_rejected(service, overrides):
    with pytest.raises(PydanticValidationError):
        _create(service, **overrides)


def test_unknown_project(service):
    with pytest.raises(NotFoundError):
        _create(service, project="nope")


def test_name_unique_per_project_case_insensitive(service):
    _create(service, name="Bot")
    _create(service, project="other", name="Bot")

    with pytest.raises(ConflictError):
        _create(service, name="bot")
    with pytest.raises(PydanticValidationError):
        _create(service, name="  ")


def test_update_bumps_the_prompt_version_only_when_the_prompt_changes(service):
    chatbot = _create(service)

    same_prompt = service.update_chatbot(
        chatbot.id, name="Bot", system_prompt=chatbot.system_prompt, model=MODEL, tool_names=["git_status"],
    )
    new_prompt = service.update_chatbot(chatbot.id, name="Bot 2", system_prompt="Nuove istruzioni.", model=MODEL)

    assert (same_prompt.prompt_version, same_prompt.tool_names) == (1, ["git_status"])
    assert (new_prompt.prompt_version, new_prompt.name, new_prompt.project_name) == (2, "Bot 2", "acme")
    assert new_prompt.updated_at > chatbot.updated_at


def test_chatbots_are_independent_from_the_library_agents(service, agent_config_service):
    _create(service)

    assert agent_config_service.delete_config("hello") is True


# ------------------------------------------------------------ conversations

def test_send_runs_the_chatbots_own_agent_on_its_project(service, agents, run_store):
    chatbot = _create(service, max_steps=7, tool_names=["git_status"])
    conversation = service.new_conversation(chatbot.id)

    reply = service.send(conversation.id, "  Ciao bot  ")

    assert (reply.role, reply.content) == (MessageRole.ASSISTANT, "echo: Ciao bot")
    [(definition, tools)] = agents.definitions
    assert (definition.system_prompt, definition.max_steps, tools) == ("Sei l'assistente del progetto.", 7, ["git_status"])
    [run] = run_store.list_runs()
    assert (run.run_id, run.origin, run.project_name) == (reply.run_id, "chat", "acme")
    assert (run.config_name, run.role_name, run.prompt_version) == ("chatbot/Bot", "chatbot", 1)


def test_send_saves_both_messages_and_titles_the_conversation(service):
    chatbot = _create(service)
    conversation = service.new_conversation(chatbot.id)

    service.send(conversation.id, "Ciao bot")

    assert [(m.role, m.content) for m in service.messages(conversation.id)] == [
        (MessageRole.USER, "Ciao bot"), (MessageRole.ASSISTANT, "echo: Ciao bot"),
    ]
    assert service.list_conversations(chatbot.id)[0].title == "Ciao bot"


def test_send_passes_the_conversation_so_far_as_memory(service, agents):
    chatbot = _create(service)
    conversation = service.new_conversation(chatbot.id)
    service.send(conversation.id, "primo")

    service.send(conversation.id, "secondo")

    turns = agents[-1].memory.to_dict()
    assert [(turn["role"], turn["blocks"][0]["content"]) for turn in turns] == [
        ("user", "primo"), ("assistant", "echo: primo"),
    ]


def test_title_is_kept_and_truncated(service):
    chatbot = _create(service)
    conversation = service.new_conversation(chatbot.id)

    service.send(conversation.id, "x" * 100)
    service.send(conversation.id, "altro")

    title = service.list_conversations(chatbot.id)[0].title
    assert len(title) == 60 and title.endswith("…")


def test_failed_run_becomes_an_error_message_kept_out_of_memory(service, agents):
    chatbot = _create(service)
    conversation = service.new_conversation(chatbot.id)
    agents.error = RuntimeError("boom")

    reply = service.send(conversation.id, "ciao")

    assert reply.role is MessageRole.ERROR and "boom" in reply.content
    assert reply.run_id is not None
    agents.error = None
    service.send(conversation.id, "di nuovo")
    assert [turn["role"] for turn in agents[-1].memory.to_dict()] == ["user"]


def test_agent_that_cannot_start_becomes_an_error_message(service, monkeypatch):
    chatbot = _create(service)
    conversation = service.new_conversation(chatbot.id)
    monkeypatch.setattr(service._agents._chat_service, "get_client", lambda model: (_ for _ in ()).throw(
        ValidationError("OPENAI_API_KEY is not set")))

    reply = service.send(conversation.id, "ciao")

    assert reply.role is MessageRole.ERROR and "OPENAI_API_KEY" in reply.content
    assert reply.run_id is None


def test_empty_message_or_unknown_conversation(service):
    chatbot = _create(service)
    conversation = service.new_conversation(chatbot.id)

    with pytest.raises(ValidationError):
        service.send(conversation.id, "   ")
    with pytest.raises(NotFoundError):
        service.send(9999, "ciao")


def test_conversations_newest_first_and_deletable(service):
    chatbot = _create(service)
    first = service.new_conversation(chatbot.id)
    second = service.new_conversation(chatbot.id)
    service.send(first.id, "ciao")

    assert [c.id for c in service.list_conversations(chatbot.id)] == [first.id, second.id]
    assert service.delete_conversation(second.id) is True
    assert [c.id for c in service.list_conversations(chatbot.id)] == [first.id]
