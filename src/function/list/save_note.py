"""save_note function: saves the step input as a markdown note of the project
(tab Dati → Note), e.g. at the end of a pipeline to keep its result."""
from datetime import datetime

from pydantic import BaseModel, Field

from core.error import ValidationError
from function.context import FunctionContext
from function.spec import FunctionResult, FunctionSpec


class Params(BaseModel):
    title: str = Field(
        "Automation {date} {time}",
        description="Nome della nota. {date} e {time} diventano data e ora (stesso nome = nota sovrascritta).",
    )


def run(context: FunctionContext, step_input: str, params: Params) -> FunctionResult:
    if not step_input.strip():
        raise ValidationError("Niente da salvare: l'input dello step è vuoto.")
    now = datetime.now().astimezone()
    title = params.title.replace("{date}", f"{now:%Y-%m-%d}").replace("{time}", f"{now:%H-%M}").strip()
    note = context.project_data.save_note(context.project_name, title, step_input)
    return FunctionResult(text=f"Nota salvata: {note.name} (tab Dati → Note).")


SAVE_NOTE = FunctionSpec(
    name="save_note",
    description="Salva l'input dello step come nota del progetto (tab Dati → Note).",
    params=Params,
    run=run,
)
