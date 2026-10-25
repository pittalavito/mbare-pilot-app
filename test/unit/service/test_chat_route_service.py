"""The chatbots' cache: the user puts one of their messages in cache with an
automation and a fixed input; a similar message then launches it directly,
without the agent (fake agents, no LLM). ``!`` skips the cache."""
import pytest

from core.error import ConflictError, ValidationError
from domain.client.embedding.embedder import HashingEmbedder
from fakes import FakeAgent
from models.domain.chatbot import MessageRole
from models.domain.pipeline import PipelineStep, RunStatus, StepAgent, StepKind
from models.domain.project import Project, ProjectSource
from service import agent_service as agent_service_module
from service.agent_service import AgentService
from service.chat_route_service import ChatRouteService
from service.chat_service import ChatService
from service.chatbot_service import ChatbotService
from service.git_service import GitService
from service.pipeline_service import PipelineService

MODEL = "openai/gpt-4o"


class _OtherEmbedder(HashingEmbedder):
    @property
    def name(self) -> str:
        return "other"


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
def pipelines(store_service, agent_config_service):
    for name in ("acme", "other"):
        store_service.save_project(Project(name=name, source=ProjectSource.FOLDER, root_path=f"/code/{name}"))
    return PipelineService(store_service, agent_config_service)


@pytest.fixture
def routes(store_service, pipelines):
    return ChatRouteService(store_service, pipelines, HashingEmbedder(), threshold=0.9)


@pytest.fixture
def chat(store_service, agent_config_service, routes, agent_runs, monkeypatch):
    llm = ChatService()
    monkeypatch.setattr(llm, "get_client", lambda model: object())
    agents = AgentService(llm, agent_config_service, store_service, GitService(store_service))
    return ChatbotService(store_service, agent_config_service, agents, routes)


@pytest.fixture
def conversation(chat):
    chatbot = chat.create_chatbot("acme", "Bot", system_prompt="Sei l'assistente.", model=MODEL)
    return chat.new_conversation(chatbot.id)


def _automation(pipelines, name="Report", project="acme"):
    step = PipelineStep(name="S", kind=StepKind.AGENT, agent=StepAgent(system_prompt="Fai.", model=MODEL))
    return pipelines.create_pipeline(project, name, steps=[step])


def _user_message(chat, conversation, text):
    chat.send(conversation.id, text)
    return next(m for m in reversed(chat.messages(conversation.id)) if m.role is MessageRole.USER)


def test_a_similar_message_launches_the_automation_without_the_agent(chat, routes, pipelines, conversation, agent_runs):
    report = _automation(pipelines)
    first = _user_message(chat, conversation, "lancia il report del giorno")
    route = routes.add(first.id, report.id, "oggi")
    assert len(agent_runs) == 1

    reply = chat.send(conversation.id, "Lancia il report del giorno!")

    [run] = pipelines.list_runs(report.id)
    assert len(agent_runs) == 1  # no new agent run
    assert reply.role is MessageRole.ASSISTANT and reply.run_id is None
    assert reply.content == f"⚡ Ho lanciato l'automation Report (id {run.id})."
    assert (run.status, run.input) == (RunStatus.QUEUED, "oggi")
    assert routes.routes(conversation.chatbot_id)[0].hits == 1 and route.text == "lancia il report del giorno"


def test_different_messages_and_bang_go_to_the_agent(chat, routes, pipelines, conversation, agent_runs):
    report = _automation(pipelines)
    routes.add(_user_message(chat, conversation, "lancia il report del giorno").id, report.id)

    chat.send(conversation.id, "come stanno i repository?")
    chat.send(conversation.id, "! lancia il report del giorno")

    assert len(agent_runs) == 3 and pipelines.list_runs(report.id) == []
    assert not chat.messages(conversation.id)[-1].content.startswith("⚡")


def test_only_entries_of_the_same_embedder_are_compared(store_service, pipelines, chat, routes, conversation):
    report = _automation(pipelines)
    routes.add(_user_message(chat, conversation, "lancia il report").id, report.id)
    other = ChatRouteService(store_service, pipelines, _OtherEmbedder(), threshold=0.9)

    assert routes.match(conversation.chatbot_id, "lancia il report").similarity == pytest.approx(1.0)
    assert other.match(conversation.chatbot_id, "lancia il report") is None


def test_an_automation_that_cannot_start_answers_with_an_error(chat, routes, pipelines, conversation):
    report = _automation(pipelines)
    routes.add(_user_message(chat, conversation, "lancia il report").id, report.id)
    pipelines.update_pipeline(report.id, name="Report", active=False, steps=report.steps)

    reply = chat.send(conversation.id, "lancia il report")

    assert reply.role is MessageRole.ERROR and "disattivata" in reply.content


def test_what_can_be_put_in_cache(chat, routes, pipelines, conversation):
    report, foreign = _automation(pipelines), _automation(pipelines, "Altro", project="other")
    message = _user_message(chat, conversation, "! lancia il report")
    answer = chat.messages(conversation.id)[-1]

    with pytest.raises(ValidationError, match="solo i tuoi messaggi"):
        routes.add(answer.id, report.id)
    with pytest.raises(ValidationError, match="non è del progetto"):
        routes.add(message.id, foreign.id)
    assert routes.add(message.id, report.id).text == "lancia il report"  # without the bypass
    with pytest.raises(ConflictError):
        routes.add(message.id, report.id)


def test_entries_survive_their_conversation(chat, routes, pipelines, conversation):
    route = routes.add(_user_message(chat, conversation, "lancia il report").id, _automation(pipelines).id)

    chat.delete_conversation(conversation.id)

    assert [entry.id for entry in routes.routes(conversation.chatbot_id)] == [route.id]
    assert routes.remove(route.id) and routes.routes(conversation.chatbot_id) == []
