"""ask_agent: delegate a question to another agent (of the Library or of the
run's project) and get its answer back. The agents the model can pick, with
their descriptions, are written into the tool description when the tool is
built for a run. The delegated run is recorded on its own (origin ``agent``);
a delegated agent cannot delegate again."""
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.tool import AskAgentResponse, ToolErrorResponse
from tool.context import ToolContext
from tool.spec import ToolSpec

MAX_DEPTH = 1
"""Delegation levels: an agent run by ask_agent gets no further delegation."""

AgentName = Annotated[str, "Exact name of the agent to ask, from the list in this tool's description."]
Question = Annotated[str, "The question or task for that agent, complete and self-contained: it does not see this conversation."]

_DESCRIPTION = (
    "Ask another agent, specialised in one source or task, and get its answer back. "
    "Use it for what you cannot answer yourself; the answer comes from that agent."
)


def build(context: ToolContext) -> Tool:
    agents = context.agents.delegable_agents(context.project_name) if context.agents else []
    listing = "\n".join(f"- {agent.name}: {agent.description or '(no description)'}" for agent in agents)
    description = f"{_DESCRIPTION}\nAvailable agents:\n{listing or '- none'}"

    @tool(name="ask_agent", description=description)
    def ask_agent(agent: AgentName, question: Question) -> str:
        if context.agents is None or context.depth >= MAX_DEPTH:
            return ToolErrorResponse(error="Delega non disponibile: questo agente è già stato chiamato da un altro agente.").model_dump_json()
        names = {candidate.name for candidate in agents}
        if agent not in names:
            available = ", ".join(sorted(names)) or "nessuno"
            return ToolErrorResponse(error=f"Agente {agent!r} non disponibile. Agenti disponibili: {available}.").model_dump_json()
        if not question.strip():
            return ToolErrorResponse(error="La domanda per l'agente è vuota.").model_dump_json()
        try:
            record = context.agents.delegate(agent, question, project_name=context.project_name, depth=context.depth + 1)
        except AppError as exc:
            return ToolErrorResponse(error=str(exc)).model_dump_json()
        if not record.ok:
            return ToolErrorResponse(error=f"L'agente {agent} non è riuscito a rispondere: {record.error}").model_dump_json()
        return AskAgentResponse(agent=agent, run_id=record.run_id, answer=record.output).model_dump_json()

    return ask_agent


ASK_AGENT = ToolSpec(
    name="ask_agent",
    description="Delega una domanda a un altro agente (della Libreria o del progetto) e ne riporta la risposta.",
    build=build,
)
