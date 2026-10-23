"""Agent factory: builds a datapizza Agent from an AgentDefinition.
Observability comes from datapizza's tracing (see domain/agent/tracing.py),
so agents need no hooks of their own."""
from datapizza.agents import Agent
from datapizza.core.clients import Client
from datapizza.memory import Memory
from datapizza.tools import Tool
from datapizza.type import ROLE, TextBlock

from models.domain.agent import AgentDefinition
from models.domain.chatbot import ChatMessage, MessageRole

_ROLES = {MessageRole.USER: ROLE.USER, MessageRole.ASSISTANT: ROLE.ASSISTANT}


class Factory:

    @staticmethod
    def create_memory(history: list[ChatMessage]) -> Memory:
        """The previous turns of a conversation, for ``agent.run(..., memory=)``.
        Error messages are left out: the agent never produced them."""
        memory = Memory()
        for message in history:
            if message.role in _ROLES:
                memory.add_turn(TextBlock(content=message.content), role=_ROLES[message.role])
        return memory

    @staticmethod
    def create_agent(definition: AgentDefinition, client: Client, tools: list[Tool]) -> Agent:
        return Agent(
            name=definition.name,
            client=client,
            system_prompt=definition.system_prompt,
            tools=tools,
            max_steps=definition.max_steps,
            terminate_on_text=True,
        )
