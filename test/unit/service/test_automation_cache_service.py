"""The chatbots' cache: the user puts one of their messages in cache with an
automation and a fixed input; a similar message then launches it directly,
without the agent (fake agents, no LLM). ``!`` skips the cache."""
import logging

import pytest

from core.error import ConflictError, UpstreamError, ValidationError
from domain.client.embedding.embedder import HashingEmbedder
from fakes import FakeAgent
from models.domain.chatbot import ChatbotKind, MessageRole
from models.domain.masking import MaskCategory
from models.domain.pipeline import PipelineStep, RunStatus, StepAgent, StepKind
from models.domain.project import Project, ProjectSource
from service import agent_service as agent_service_module
from service.agent_service import AgentService
from service.automation_cache_service import AutomationCacheService
from service.chat_service import ChatService
from service.chatbot_service import ChatbotService
from service.git_service import GitService
from service.masking_service import MaskingService
from service.pipeline_service import PipelineService

MODEL = "openai/gpt-4o"


class _OtherEmbedder(HashingEmbedder):
    @property
    def name(self) -> str:
        return "other"


class _RemoteEmbedder(HashingEmbedder):
    """Sends the text outside the PC (as OpenRouter): records what it receives."""

    def __init__(self):
        super().__init__()
        self.received = []

    @property
    def name(self) -> str:
        return "remote"

    @property
    def local(self) -> bool:
        return False

    def embed(self, text):
        self.received.append(text)
        return super().embed(text)


class _DownEmbedder(HashingEmbedder):
    @property
    def name(self) -> str:
        return "down"

    def embed(self, text):
        raise UpstreamError("OpenRouter non risponde")


@pytest.fixture
def agent_runs(monkeypatch):
    """The fake agents built: one per message answered by the agent."""
    built = []

    def create_agent(definition, client, tools):
        built.append(FakeAgent())
        return built[-1]

    monkeypatch.setattr(agent_service_module.AgentFactory, "create_agent", staticmethod(create_agent))
    return built


@pytest.fixture
def pipelines(store_service, agent_config_service, worker_store):
    for name in ("acme", "other"):
        store_service.save_project(Project(name=name, source=ProjectSource.FOLDER, root_path=f"/code/{name}"))
    return PipelineService(store_service, agent_config_service, worker_store)


@pytest.fixture
def cache(store_service, pipelines):
    return AutomationCacheService(store_service, pipelines, HashingEmbedder(), threshold=0.9)


@pytest.fixture
def chat(store_service, agent_config_service, cache, agent_runs, monkeypatch):
    llm = ChatService()
    monkeypatch.setattr(llm, "get_client", lambda model: object())
    agents = AgentService(llm, agent_config_service, store_service, GitService(store_service))
    return ChatbotService(store_service, agent_config_service, agents, cache)


@pytest.fixture
def conversation(chat):
    chatbot = chat.create_chatbot("acme", "Bot", system_prompt="Sei l'assistente.", model=MODEL, kind=ChatbotKind.AUTOMATION)
    return chat.new_conversation(chatbot.id)


def _automation(pipelines, name="Report", project="acme"):
    step = PipelineStep(name="S", kind=StepKind.AGENT, agent=StepAgent(system_prompt="Fai.", model=MODEL))
    return pipelines.create_pipeline(project, name, steps=[step])


def _user_message(chat, conversation, text):
    chat.send(conversation.id, text)
    return next(m for m in reversed(chat.messages(conversation.id)) if m.role is MessageRole.USER)


def test_a_similar_message_launches_the_automation_without_the_agent(chat, cache, pipelines, conversation, agent_runs):
    report = _automation(pipelines)
    first = _user_message(chat, conversation, "lancia il report del giorno")
    entry = cache.add(first.id, report.id, "oggi")
    assert len(agent_runs) == 1

    reply = chat.send(conversation.id, "Lancia il report del giorno!")

    [run] = pipelines.list_runs(report.id)
    assert len(agent_runs) == 1  # no new agent run
    assert reply.role is MessageRole.ASSISTANT and reply.run_id is None
    assert reply.content == f"⚡ Ho lanciato l'automation Report (id {run.id})."
    assert (run.status, run.input) == (RunStatus.QUEUED, "oggi")
    assert cache.entries(conversation.chatbot_id)[0].hits == 1 and entry.text == "lancia il report del giorno"


def test_different_messages_and_bang_go_to_the_agent(chat, cache, pipelines, conversation, agent_runs):
    report = _automation(pipelines)
    cache.add(_user_message(chat, conversation, "lancia il report del giorno").id, report.id)

    chat.send(conversation.id, "come stanno i repository?")
    chat.send(conversation.id, "! lancia il report del giorno")

    assert len(agent_runs) == 3 and pipelines.list_runs(report.id) == []
    assert not chat.messages(conversation.id)[-1].content.startswith("⚡")


def test_entries_of_another_embedder_are_embedded_again_and_kept(store_service, pipelines, chat, cache, conversation):
    report = _automation(pipelines)
    cache.add(_user_message(chat, conversation, "lancia il report").id, report.id)
    other = AutomationCacheService(store_service, pipelines, _OtherEmbedder(), threshold=0.9)

    assert other.match(conversation.chatbot_id, "lancia il report").similarity == pytest.approx(1.0)
    assert [entry.embedder for entry in other.entries(conversation.chatbot_id)] == ["other"]  # saved with the new one


def test_an_automation_that_cannot_start_answers_with_an_error(chat, cache, pipelines, conversation):
    report = _automation(pipelines)
    cache.add(_user_message(chat, conversation, "lancia il report").id, report.id)
    pipelines.update_pipeline(report.id, name="Report", active=False, steps=report.steps)

    reply = chat.send(conversation.id, "lancia il report")

    assert reply.role is MessageRole.ERROR and "disattivata" in reply.content


def test_what_can_be_put_in_cache(chat, cache, pipelines, conversation):
    report, foreign = _automation(pipelines), _automation(pipelines, "Altro", project="other")
    message = _user_message(chat, conversation, "! lancia il report")
    answer = chat.messages(conversation.id)[-1]

    with pytest.raises(ValidationError, match="solo i tuoi messaggi"):
        cache.add(answer.id, report.id)
    with pytest.raises(ValidationError, match="non è del progetto"):
        cache.add(message.id, foreign.id)
    assert cache.add(message.id, report.id).text == "lancia il report"  # without the bypass
    with pytest.raises(ConflictError):
        cache.add(message.id, report.id)


def test_entries_survive_their_conversation(chat, cache, pipelines, conversation):
    entry = cache.add(_user_message(chat, conversation, "lancia il report").id, _automation(pipelines).id)

    chat.delete_conversation(conversation.id)

    assert [entry.id for entry in cache.entries(conversation.chatbot_id)] == [entry.id]
    assert cache.remove(entry.id) and cache.entries(conversation.chatbot_id) == []


# ------------------------------------------------- real embedders, logs

def test_a_remote_embedder_only_gets_masked_text(store_service, pipelines, chat, conversation, mask_store):
    masking = MaskingService(store_service, mask_store)
    masking.add_term("acme", MaskCategory.PERSON, "Mario Rossi")
    remote = _RemoteEmbedder()
    cache = AutomationCacheService(store_service, pipelines, remote, threshold=0.9, masking_service=masking)

    cache.add(_user_message(chat, conversation, "report di Mario Rossi").id, _automation(pipelines).id)
    cache.match(conversation.chatbot_id, "report di Mario Rossi")

    assert remote.received == ["report di PERSONA_1", "report di PERSONA_1"]


def test_a_remote_embedder_without_masking_is_refused(store_service, pipelines):
    with pytest.raises(ValidationError, match="mascheramento"):
        AutomationCacheService(store_service, pipelines, _RemoteEmbedder(), threshold=0.9)


def test_if_embedding_fails_the_agent_answers(store_service, pipelines, chat, cache, conversation, agent_runs, caplog):
    cache.add(_user_message(chat, conversation, "lancia il report").id, _automation(pipelines).id)
    down = AutomationCacheService(store_service, pipelines, _DownEmbedder(), threshold=0.9)

    with caplog.at_level(logging.WARNING):
        assert down.match(conversation.chatbot_id, "lancia il report") is None
    assert "non consultata" in caplog.text and "OpenRouter non risponde" in caplog.text


def test_every_comparison_is_logged_with_its_similarities(chat, cache, pipelines, conversation, caplog):
    entry = cache.add(_user_message(chat, conversation, "lancia il report").id, _automation(pipelines).id)

    with caplog.at_level(logging.INFO):
        cache.match(conversation.chatbot_id, "lancia il report")
        cache.match(conversation.chatbot_id, "stato dei repository")

    assert f"voce {entry.id}=1.000 · soglia 0.90 → voce {entry.id}, lancio l'automation" in caplog.text
    assert f"voce {entry.id}=0.000 · soglia 0.90 → nessuna voce, risponde l'agente" in caplog.text


def test_only_an_automation_chatbot_has_the_cache_and_each_kind_its_fixed_tools(chat, cache, pipelines, conversation, agent_runs):
    report = _automation(pipelines)
    custom = chat.create_chatbot("acme", "Libero", system_prompt="Fai tu.", model=MODEL, tool_names=["git_status"])
    talk = chat.new_conversation(custom.id)
    with pytest.raises(ValidationError, match="solo dei chatbot di tipo automation"):
        cache.add(_user_message(chat, talk, "lancia il report").id, report.id)

    automation = chat.get_chatbot(conversation.chatbot_id)
    assert automation.tool_names == ["list_automations", "run_automation", "automation_status"]
    edited = chat.update_chatbot(automation.id, name="Bot", system_prompt="Sei l'assistente.", model=MODEL, tool_names=["git_status"])
    assert edited.kind is ChatbotKind.AUTOMATION and edited.tool_names == automation.tool_names  # imposed, whatever is asked
    assert chat.update_chatbot(custom.id, name="Libero", system_prompt="Fai tu.", model=MODEL, tool_names=["git_status"]).tool_names == ["git_status"]


    secretary = chat.create_chatbot("acme", "Segretario", system_prompt="Note.", model=MODEL, tool_names=["git_status"], kind=ChatbotKind.SECRETARY)
    assert secretary.tool_names == ["list_todo_lists", "read_todo_list", "create_todo_list", "update_todo_list", "list_agent_tasks"]
    with pytest.raises(ValidationError, match="solo dei chatbot di tipo automation"):
        cache.add(_user_message(chat, chat.new_conversation(secretary.id), "lancia il report").id, report.id)
