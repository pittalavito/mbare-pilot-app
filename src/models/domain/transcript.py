"""«🔍 Cosa ha visto il modello»: one run's exchange with the
model, masked (as it left) and in clear."""
from pydantic import BaseModel, Field

from models.domain.agent import ModelMessage


class TranscriptTool(BaseModel):
    name: str
    arguments: str = ""
    result: str = ""
    error: str | None = None


class TranscriptView(BaseModel):
    system_prompt: str = ""
    history: list[ModelMessage] = Field(default_factory=list)
    input: str = ""
    tool_calls: list[TranscriptTool] = Field(default_factory=list)
    output: str = ""


class RunTranscript(BaseModel):
    run_id: str
    project_name: str | None = None
    masked: TranscriptView
    clear: TranscriptView
    aliases: list[str] = Field(default_factory=list)
    """The aliases of the project's map: the UI highlights them in the masked view."""
