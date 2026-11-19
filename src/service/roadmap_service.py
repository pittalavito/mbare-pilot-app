"""The board of Mbare Pilot (plan 30): ``roadmap.yml`` read from the
definitions (the data folder's wins over the app's, like the other files)
and validated. Read only: the board is changed in the file."""
import yaml
from pydantic import ValidationError as PydanticValidationError

from core.error import ValidationError
from models.domain.roadmap import Roadmap
from service.store.definition_store import DefinitionStore

ROADMAP_FILE = "roadmap.yml"


class RoadmapService:

    def __init__(self, definitions: DefinitionStore):
        self._definitions = definitions

    def roadmap(self) -> Roadmap:
        """The board; empty without the file. 400 when the file is broken."""
        text = self._definitions.read_definition(ROADMAP_FILE)
        if text is None:
            return Roadmap()
        try:
            return Roadmap.model_validate(yaml.safe_load(text) or {})
        except (yaml.YAMLError, PydanticValidationError) as exc:
            raise ValidationError(f"{ROADMAP_FILE} non valido: {exc}") from exc
