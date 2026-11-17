"""The structured answers an agent of the Library can give (``output:`` in
global-agent.yml): the code reads their fields to create activities and tasks."""
from pydantic import BaseModel

from models.domain.activity_draft import DraftAnswer
from models.domain.plan import PlanAnswer
from models.domain.wip import WipAnswer

WIP = "wip"
PLAN = "plan"
DRAFT = "draft"

STRUCTURED_OUTPUTS: dict[str, type[BaseModel]] = {WIP: WipAnswer, PLAN: PlanAnswer, DRAFT: DraftAnswer}
"""Name → schema."""

OUTPUT_DESCRIPTIONS = {
    WIP: "«Elabora WIP»: proposte per le attività dalla nota WIP",
    PLAN: "Pianificatore di «▶️ Lavora attività»: gli agent task in ordine",
    DRAFT: "«📎 Da riferimenti»: titolo, descrizione e voci di una nuova attività",
}

WIP_AGENT = "wip"
PLAN_AGENT = "pianificatore"
DRAFT_AGENT = "bozza-attivita"
"""The agents of global-agent.yml the code calls by name."""
