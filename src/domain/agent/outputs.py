"""The structured answers an agent of the Library can give (``output:`` in
agents/agents.yml): the code reads their fields to create activities and tasks."""
from pydantic import BaseModel

from models.domain.activity_close import LearnedAnswer
from models.domain.activity_draft import DraftAnswer
from models.domain.code_search import RegexAnswer
from models.domain.plan import PlanAnswer
from models.domain.wip import WipAnswer

WIP = "wip"
PLAN = "plan"
DRAFT = "draft"
LEARNED = "learned"
REGEX = "regex"

STRUCTURED_OUTPUTS: dict[str, type[BaseModel]] = {WIP: WipAnswer, PLAN: PlanAnswer, DRAFT: DraftAnswer, LEARNED: LearnedAnswer, REGEX: RegexAnswer}
"""Name → schema."""

OUTPUT_DESCRIPTIONS = {
    WIP: "«Elabora WIP»: proposte per le attività dalla nota WIP",
    PLAN: "Pianificatore di «▶️ Lavora attività»: gli agent task in ordine",
    DRAFT: "«📎 Da riferimenti»: titolo, descrizione e voci di una nuova attività",
    LEARNED: "Step «Chiudi»: cosa ha insegnato un'attività, per context/imparato.md",
    REGEX: "«✨ Regex»: una regex per le ricerche salvate, con spiegazione ed esempio",
}

WIP_AGENT = "wip"
PLAN_AGENT = "pianificatore"
DRAFT_AGENT = "bozza-attivita"
LEARNED_AGENT = "imparato"
REGEX_AGENT = "regex"
"""The agents of agents/agents.yml the code calls by name."""
