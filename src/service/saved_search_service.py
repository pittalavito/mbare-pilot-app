"""Saved searches in the code («regex parlanti»): a name for a regex
(or a text) and its file filter, chosen from a menu in «🔎 Cerca nel codice»
and in «Nuovo riferimento» from code.

The defaults are in ``board/code-searches.yml`` of the definitions (the data
folder's file wins over the app's, like the roadmap); the project's own are in
its settings and replace a default with the same name. «✨ Regex» asks the
agent ``regex`` of agents/agents.yml (one structured call, masked like the
other agents) for a regex from a description in words; the answer is checked
(it compiles, it finds its own example) before the user tries it."""
import json
import re

import yaml
from pydantic import ValidationError as PydanticValidationError

from core.error import NotFoundError, UpstreamError, ValidationError
from core.observability import LogPrefix, observed
from domain.agent.outputs import REGEX, REGEX_AGENT
from domain.masking.preview import masked_text, unmask
from domain.project.data_paths import SEARCHES_FILE
from models.domain.agent import RunOrigin
from models.domain.code_search import RegexAnswer, RegexProposal, SavedSearch, SavedSearchFile, SavedSearchView
from models.domain.project import Project
from service.masking_service import MaskingService
from service.store.definition_store import DefinitionStore
from service.store.project_store import ProjectStore
from service.structured_agent_service import StructuredAgentService

APP, PROJECT = "app", "progetto"
MAX_DESCRIPTION_CHARS = 1000


class SavedSearchService:

    def __init__(self, definitions: DefinitionStore, projects: ProjectStore, masking: MaskingService, agents: StructuredAgentService):
        self._definitions = definitions
        self._projects = projects
        self._masking = masking
        self._agents = agents

    def defaults(self) -> list[SavedSearch]:
        """The searches of ``board/code-searches.yml``; none without the file, 400 when it is broken."""
        text = self._definitions.read_definition(SEARCHES_FILE)
        if text is None:
            return []
        try:
            return SavedSearchFile.model_validate(yaml.safe_load(text) or {}).searches
        except (yaml.YAMLError, PydanticValidationError) as exc:
            raise ValidationError(f"{SEARCHES_FILE} non valido: {exc}") from exc

    def searches(self, project_name: str) -> list[SavedSearchView]:
        """The defaults (in the file's order, the project's version where it has one), then the project's others."""
        own = {search.name: search for search in self._project(project_name).code_searches}
        views = [SavedSearchView(**own.pop(search.name).model_dump(), origin=PROJECT) if search.name in own
                 else SavedSearchView(**search.model_dump(), origin=APP) for search in self.defaults()]
        return views + [SavedSearchView(**search.model_dump(), origin=PROJECT) for search in own.values()]

    @observed(LogPrefix.CODE_SEARCH_SERVICE)
    def save(self, project_name: str, search: SavedSearch, replacing: str = "") -> list[SavedSearchView]:
        """The search in the project (by name: a new one, the same name rewritten, ``replacing`` renamed);
        400 for a broken regex."""
        search = search.model_copy(update={"name": " ".join(search.name.split()), "files": search.files.strip()})
        if search.regex:
            _compile(search.query)
        project = self._project(project_name)
        gone = {search.name, replacing.strip()}
        searches = [item for item in project.code_searches if item.name not in gone] + [search]
        self._projects.save(project.model_copy(update={"code_searches": searches}))
        return self.searches(project_name)

    @observed(LogPrefix.CODE_SEARCH_SERVICE)
    def delete(self, project_name: str, name: str) -> list[SavedSearchView]:
        """The project's search gone (a default it replaced comes back); 404 when the project has none with that name."""
        project = self._project(project_name)
        searches = [item for item in project.code_searches if item.name != name]
        if len(searches) == len(project.code_searches):
            raise NotFoundError(f"Ricerca del progetto non trovata: {name}")
        self._projects.save(project.model_copy(update={"code_searches": searches}))
        return self.searches(project_name)

    @observed(LogPrefix.CODE_SEARCH_SERVICE)
    def propose_regex(self, project_name: str, description: str) -> RegexProposal:
        """«✨ Regex»: one call to the agent ``regex``; the regex checked against its example."""
        description = description.strip()[:MAX_DESCRIPTION_CHARS]
        if not description:
            raise ValidationError("Scrivi cosa vuoi cercare.")
        self._project(project_name)
        agent = self._agents.agent(REGEX_AGENT, REGEX)
        entries = self._masking.entries(project_name)
        masked = masked_text(description, entries)
        call = self._agents.call(agent, masked.text)
        clear = lambda text: unmask(text, entries, masked.temporary).strip()  # noqa: E731
        answer = call.answer if isinstance(call.answer, RegexAnswer) else None
        found = RegexAnswer(regex=clear(answer.regex), explanation=clear(answer.explanation), example=clear(answer.example)) if answer else RegexAnswer()
        run_id = self._agents.save(call, project_name=project_name, origin=RunOrigin.REGEX, input=description,
                                   output=json.dumps(found.model_dump(mode="json"), ensure_ascii=False))
        if call.error is not None or not found.regex:
            raise UpstreamError(f"L'agente {agent.name} non ha risposto: {call.error or 'nessuna regex'}")
        try:
            pattern = _compile(found.regex)
        except ValidationError:
            pattern = None
        return RegexProposal(**found.model_dump(), valid=pattern is not None,
                             example_matches=bool(pattern and found.example and pattern.search(found.example)),
                             run_id=run_id, cost_eur=round(call.telemetry.total_tokens.cost_eur, 6))

    def _project(self, project_name: str) -> Project:
        project = self._projects.get(project_name)
        if project is None:
            raise NotFoundError(f"Progetto non trovato: {project_name}")
        return project


def _compile(regex: str) -> re.Pattern[str]:
    try:
        return re.compile(regex)
    except re.error as exc:
        raise ValidationError(f"Regex non valida: {exc}") from exc
