"""save_note: saves a text as a markdown note of the project (Progetto → Note),
e.g. at the end of an automation to keep its result (``content: "{input}"``)."""
from datetime import datetime

from pydantic import BaseModel, Field

from core.error import ValidationError
from tool.context import ToolContext
from tool.spec import params_tool


class Params(BaseModel):
    title: str = Field(
        "Automation {date} {time}",
        description="Nome della nota. {date} e {time} diventano data e ora (stesso nome = nota sovrascritta).",
    )
    content: str = Field(..., description="Il testo della nota (markdown); in un'automation di solito «{input}», l'output dello step prima.")


class Result(BaseModel):
    text: str


def run(context: ToolContext, params: Params) -> Result:
    if not params.content.strip():
        raise ValidationError("Niente da salvare: il testo è vuoto.")
    now = datetime.now().astimezone()
    title = params.title.replace("{date}", f"{now:%Y-%m-%d}").replace("{time}", f"{now:%H-%M}").strip()
    note = context.require_project_data().save_note(context.require_project(), title, params.content)
    return Result(text=f"Nota salvata: {note.name} (Progetto → Note).")


SAVE_NOTE = params_tool(
    "save_note",
    "Saves a text as a markdown note of the project (Progetto → Note); the same name overwrites it.",
    Params, run, writes=True,
)
