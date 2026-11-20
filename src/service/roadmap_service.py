"""The board of Mbare Pilot: ``roadmap.yml`` of the definitions, read (the
data folder's wins over the app's, like the other files) and written by the UI
into the data folder: header (goal, vision) and cards (new, changed, moved,
deleted). Every card has a stable ``id``; one without (written by hand) gets
it from its title, and keeps it once the board is saved."""
import re
import unicodedata

import yaml
from pydantic import ValidationError as PydanticValidationError

from core.error import NotFoundError, ValidationError
from core.observability import LogPrefix, observed
from models.domain.roadmap import Roadmap, RoadmapCard, RoadmapItem, RoadmapStatus
from service.store.definition_store import DefinitionStore

ROADMAP_FILE = "roadmap.yml"
_HEADER = ("# La bacheca di Mbare Pilot: le modifiche future dell'app. La scrive la UI («🚀 Mbare Pilot»), si può anche a mano.\n"
           "# status: todo | in_progress | done · priority: high | medium | low\n"
           "# kind: bug | funzione | refactoring | documentazione | integrazione | uso | progettazione | rag\n"
           "# owner: tu | claude | copilot | agente remoto\n\n")


class RoadmapService:

    def __init__(self, definitions: DefinitionStore):
        self._definitions = definitions

    def roadmap(self) -> Roadmap:
        """The board; empty without the file. 400 when the file is broken."""
        text = self._definitions.read_definition(ROADMAP_FILE)
        if text is None:
            return Roadmap()
        try:
            board = Roadmap.model_validate(yaml.safe_load(text) or {})
        except (yaml.YAMLError, PydanticValidationError) as exc:
            raise ValidationError(f"{ROADMAP_FILE} non valido: {exc}") from exc
        taken: set[str] = set()
        for item in board.items:
            item.id = _unique(item.id or _slug(item.title), taken)
            taken.add(item.id)
        return board

    @observed(LogPrefix.ROADMAP_SERVICE)
    def save_header(self, goal: str, vision: str) -> Roadmap:
        board = self.roadmap()
        return self._write(board.model_copy(update={"goal": goal.strip(), "vision": vision.strip()}))

    @observed(LogPrefix.ROADMAP_SERVICE)
    def add(self, card: RoadmapCard) -> Roadmap:
        """The card at the end of the board, with a new id."""
        board = self.roadmap()
        item = RoadmapItem(**_clean(card).model_dump(), id=_unique(_slug(card.title), {item.id for item in board.items}))
        return self._write(board.model_copy(update={"items": [*board.items, item]}))

    @observed(LogPrefix.ROADMAP_SERVICE)
    def update(self, item_id: str, card: RoadmapCard) -> Roadmap:
        """The card changed in place (same id); 404 when there is none."""
        board = self.roadmap()
        self._find(board, item_id)
        items = [RoadmapItem(**_clean(card).model_dump(), id=item.id) if item.id == item_id else item for item in board.items]
        return self._write(board.model_copy(update={"items": items}))

    @observed(LogPrefix.ROADMAP_SERVICE)
    def move(self, item_id: str, status: RoadmapStatus) -> Roadmap:
        """The card to another column (dragged, or «Sposta»)."""
        board = self.roadmap()
        self._find(board, item_id).status = status
        return self._write(board)

    @observed(LogPrefix.ROADMAP_SERVICE)
    def delete(self, item_id: str) -> Roadmap:
        board = self.roadmap()
        self._find(board, item_id)
        return self._write(board.model_copy(update={"items": [item for item in board.items if item.id != item_id]}))

    def _find(self, board: Roadmap, item_id: str) -> RoadmapItem:
        found = next((item for item in board.items if item.id == item_id), None)
        if found is None:
            raise NotFoundError(f"Scheda non trovata: {item_id}")
        return found

    def _write(self, board: Roadmap) -> Roadmap:
        """Into the data folder (the app's file stays as the starting point)."""
        data: dict = {"goal": board.goal, "vision": board.vision,
                      "items": [_item_data(item) for item in board.items]}
        if not board.goal:
            data.pop("goal")
        if not board.vision:
            data.pop("vision")
        text = _HEADER + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120)
        self._definitions.save_definition(ROADMAP_FILE, text)
        return self.roadmap()


def _clean(card: RoadmapCard) -> RoadmapCard:
    return card.model_copy(update={field: getattr(card, field).strip() for field in ("title", "description", "kind", "owner", "feasibility")})


def _item_data(item: RoadmapItem) -> dict:
    """Only what is set, id first."""
    data = item.model_dump(mode="json")
    ordered = {"id": data.pop("id"), **data}
    return {key: value for key, value in ordered.items() if value not in ("", None) and not (key == "status" and value == "todo")}


def _slug(title: str) -> str:
    text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60] or "scheda"


def _unique(base: str, taken: set[str]) -> str:
    candidate, number = base, 2
    while candidate in taken:
        candidate, number = f"{base}-{number}", number + 1
    return candidate
