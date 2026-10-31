"""Jira and Confluence on Atlassian Cloud (``https://<site>.atlassian.net``),
configured per project.

``AtlassianService`` keeps each project's site settings (table
project_atlassian) and hands out an ``AtlassianSite`` for a project: the one
entry point for the rest of the app (UI, agent tools), which validates inputs
before they reach JQL/CQL. It also copies an issue or a page into the project
as a context reference (``reference_from_issue`` / ``reference_from_page``)."""
import re

from pydantic import SecretStr

from core.error import NotFoundError, ValidationError
from core.observability import LogPrefix, observed
from domain.client.atlassian.client import AtlassianHttp, ConfluenceClient, JiraClient
from models.domain.atlassian import (
    AtlassianFavorite,
    AtlassianSettings,
    AtlassianUser,
    ConfluencePage,
    ConfluenceSearchHit,
    ConfluenceSpace,
    FavoriteKind,
    JiraIssue,
    JiraProject,
)
from models.domain.note import NoteType, Reference
from service.project_data_service import ProjectDataService
from service.store.atlassian_store import AtlassianStore
from service.store.project_store import ProjectStore

_PROJECT_KEY = re.compile(r"^[A-Z][A-Z0-9_]{1,9}$")
_ISSUE_KEY = re.compile(r"^[A-Z][A-Z0-9_]{1,9}-\d+$")
_SPACE_KEY = re.compile(r"^~?[A-Za-z0-9_]{1,255}$")


class AtlassianService:

    def __init__(self, atlassian: AtlassianStore, projects: ProjectStore, project_data_service: ProjectDataService | None = None):
        """``project_data_service``: to copy issues and pages into the project as references."""
        self._atlassian = atlassian
        self._projects = projects
        self._data = project_data_service
        self._sites: dict[str, tuple[AtlassianSettings, AtlassianSite]] = {}
        """Built sites per project, rebuilt when the project's settings change."""

    def get_settings(self, project_name: str) -> AtlassianSettings | None:
        return self._atlassian.get_settings(project_name)

    def is_configured(self, project_name: str) -> bool:
        settings = self.get_settings(project_name)
        return settings is not None and settings.is_complete

    @observed(LogPrefix.ATLASSIAN_SERVICE)
    def save_settings(
        self,
        project_name: str,
        *,
        base_url: str,
        email: str,
        api_token: str = "",
        jira_project_key: str = "",
        confluence_space_key: str = "",
    ) -> AtlassianSettings:
        """Set the project's site. An empty ``api_token`` keeps the saved one.
        The favorites of any other site are dropped (same site = kept, also
        after removing and adding the settings again)."""
        if self._projects.get(project_name) is None:
            raise NotFoundError(f"Progetto non trovato: {project_name}")
        base_url = base_url.strip().rstrip("/")
        if not re.match(r"^https://[^/\s]+$", base_url):
            raise ValidationError(f"URL del sito non valido: {base_url!r} (es. https://acme.atlassian.net).")
        if not email.strip():
            raise ValidationError("L'email è obbligatoria.")
        token = api_token.strip()
        if not token:
            saved = self.get_settings(project_name)
            token = saved.api_token.get_secret_value() if saved else ""
        if not token:
            raise ValidationError("L'API token è obbligatorio.")
        jira_key = _project_key(jira_project_key) if jira_project_key.strip() else ""
        space_key = _space_key(confluence_space_key) if confluence_space_key.strip() else ""
        settings = self._atlassian.save_settings(AtlassianSettings(
            project_name=project_name,
            base_url=base_url,
            email=email.strip(),
            api_token=SecretStr(token),
            jira_project_key=jira_key,
            confluence_space_key=space_key,
        ))
        self._atlassian.delete_favorites_of_other_sites(project_name, base_url)
        return settings

    def remove_settings(self, project_name: str) -> bool:
        self._sites.pop(project_name, None)
        return self._atlassian.delete_settings(project_name)

    # ------------------------------------------------------------ favorites
    def list_favorites(self, project_name: str) -> list[AtlassianFavorite]:
        """The project's favorite issues and pages, oldest first."""
        return self._atlassian.list_favorites(project_name)

    def add_favorite(self, project_name: str, kind: FavoriteKind, ref: str, title: str, url: str) -> AtlassianFavorite:
        """Save an issue or page of the project's site as a favorite; already a
        favorite = returned as it is. ValidationError when Atlassian is not configured."""
        if self._projects.get(project_name) is None:
            raise NotFoundError(f"Progetto non trovato: {project_name}")
        settings = self._require_settings(project_name)
        ref = ref.strip().upper() if kind is FavoriteKind.JIRA_ISSUE else ref.strip()
        if not ref or not title.strip():
            raise ValidationError("Il preferito deve avere un riferimento e un titolo.")
        existing = self._atlassian.find_favorite(project_name, kind, ref)
        if existing is not None:
            return existing
        return self._atlassian.save_favorite(AtlassianFavorite(
            project_name=project_name,
            kind=kind,
            ref=ref,
            site=settings.base_url,
            title=title.strip(),
            url=url.strip(),
        ))

    def remove_favorite(self, project_name: str, favorite_id: int) -> None:
        favorite = self._atlassian.get_favorite(favorite_id)
        if favorite is None or favorite.project_name != project_name:
            raise NotFoundError(f"Preferito non trovato: {favorite_id}")
        self._atlassian.delete_favorite(favorite_id)

    # ----------------------------------------------------------- references
    @observed(LogPrefix.ATLASSIAN_SERVICE)
    def reference_from_issue(self, project_name: str, issue_key: str, link_to: list[str] = ()) -> tuple[str, bool]:
        """The issue as a context reference (``source`` jira), linked from
        ``link_to``; a second time it is refreshed. Returns (name, created)."""
        issue = self.site(project_name).get_issue(issue_key)
        return self._import(project_name, issue_reference(issue), link_to)

    @observed(LogPrefix.ATLASSIAN_SERVICE)
    def reference_from_page(self, project_name: str, page_id: str, link_to: list[str] = ()) -> tuple[str, bool]:
        """The page as a context reference (``source`` confluence), as above."""
        page = self.site(project_name).get_page(page_id)
        return self._import(project_name, page_reference(page), link_to)

    def _import(self, project_name: str, reference: Reference, link_to: list[str]) -> tuple[str, bool]:
        if self._data is None:
            raise ValidationError("Copia nei riferimenti non disponibile.")
        return self._data.import_reference(project_name, NoteType.CONTEXT_REFERENCE, reference, list(link_to))

    def site(self, project_name: str) -> "AtlassianSite":
        """The project's Atlassian site; ValidationError when not configured."""
        settings = self._require_settings(project_name)
        cached = self._sites.get(project_name)
        if cached and cached[0] == settings:
            return cached[1]
        site = build_site(settings)
        self._sites[project_name] = (settings, site)
        return site

    def _require_settings(self, project_name: str) -> AtlassianSettings:
        settings = self.get_settings(project_name)
        if settings is None or not settings.is_complete:
            raise ValidationError(f"Atlassian non configurato per il progetto {project_name}: impostalo in Impostazioni → Atlassian.")
        return settings


def issue_reference(issue: JiraIssue) -> Reference:
    """``NAV-7 · summary``, its facts, then the description."""
    facts = [f"{label}: {value}" for label, value in (
        ("Tipo", issue.issue_type), ("Stato", issue.status), ("Priorità", issue.priority), ("Assegnata a", issue.assignee),
    ) if value]
    content = "\n\n".join(part for part in (" · ".join(facts), issue.description.strip()) if part)
    return Reference(title=f"{issue.key} · {issue.summary}", source="jira", source_url=issue.url, content=content)


def page_reference(page: ConfluencePage) -> Reference:
    return Reference(title=page.title, source="confluence", source_url=page.url, content=page.body.strip())


def build_site(settings: AtlassianSettings) -> "AtlassianSite":
    """Clients for the site in ``settings`` (assumed complete)."""
    http = AtlassianHttp(settings.base_url, settings.email, settings.api_token.get_secret_value())
    return AtlassianSite(
        JiraClient(http),
        ConfluenceClient(http),
        jira_project_key=settings.jira_project_key or None,
        confluence_space_key=settings.confluence_space_key or None
    )


class AtlassianSite:
    """One Atlassian Cloud site, with the project's default Jira project and
    Confluence space (used when a call does not name one)."""

    def __init__(
        self,
        jira: JiraClient,
        confluence: ConfluenceClient,
        jira_project_key: str | None = None,
        confluence_space_key: str | None = None,
    ):
        self._jira = jira
        self._confluence = confluence
        self.jira_project_key = jira_project_key
        self.confluence_space_key = confluence_space_key

    @observed(LogPrefix.ATLASSIAN_SERVICE)
    def check_connection(self) -> AtlassianUser:
        """The account behind the API token: proves URL and credentials work."""
        return self._jira.myself()

    # ---------------------------------------------------------------- Jira
    def list_jira_projects(self, query: str | None = None, limit: int = 100) -> list[JiraProject]:
        return self._jira.list_projects(query=query or None, limit=limit)

    def search_issues(self, jql: str, limit: int = 50) -> list[JiraIssue]:
        if not jql.strip():
            raise ValidationError("La query JQL è vuota.")
        return self._jira.search_issues(jql, limit=limit)

    def project_issues(self, project_key: str | None = None, limit: int = 50, open_only: bool = False) -> list[JiraIssue]:
        """Issues of one Jira project (default: the project's), most recently updated first."""
        key = _project_key(self._default(project_key, self.jira_project_key, "progetto Jira"))
        jql = f'project = "{key}"' + (" AND statusCategory != Done" if open_only else "") + " ORDER BY updated DESC"
        return self._jira.search_issues(jql, limit=limit)

    def get_issue(self, issue_key: str) -> JiraIssue:
        key = issue_key.strip().upper()
        if not _ISSUE_KEY.match(key):
            raise ValidationError(f"Chiave issue non valida: {issue_key!r} (es. PROJ-123).")
        return self._jira.get_issue(key)

    # ---------------------------------------------------------- Confluence
    def list_spaces(self, limit: int = 100) -> list[ConfluenceSpace]:
        return self._confluence.list_spaces(limit=limit)

    def list_space_pages(self, space_key: str | None = None, limit: int = 100) -> list[ConfluencePage]:
        """Pages of one space (default: the project's)."""
        key = _space_key(self._default(space_key, self.confluence_space_key, "spazio Confluence"))
        space = self._confluence.get_space(key)
        if space is None:
            raise NotFoundError(f"Spazio Confluence non trovato: {key}")
        return self._confluence.list_pages(space.id, limit=limit)

    def get_page(self, page_id: str) -> ConfluencePage:
        if not page_id.strip().isdigit():
            raise ValidationError(f"Id pagina non valido: {page_id!r}")
        return self._confluence.get_page(page_id.strip())

    def search_pages(self, text: str, space_key: str | None = None, limit: int = 25) -> list[ConfluenceSearchHit]:
        """Full-text search, in one space or (``space_key`` None) in all of them."""
        if not text.strip():
            raise ValidationError("Il testo da cercare è vuoto.")
        return self._confluence.search_pages(text.strip(), space_key=space_key or None, limit=limit)

    @staticmethod
    def _default(value: str | None, default: str | None, what: str) -> str:
        if value and value.strip():
            return value
        if default:
            return default
        raise ValidationError(f"Nessun {what} indicato e nessuno predefinito per il progetto.")


def _project_key(value: str) -> str:
    key = value.strip().upper()
    if not _PROJECT_KEY.match(key):
        raise ValidationError(f"Chiave progetto Jira non valida: {value!r} (es. PROJ).")
    return key


def _space_key(value: str) -> str:
    key = value.strip()
    if not _SPACE_KEY.match(key):
        raise ValidationError(f"Chiave spazio Confluence non valida: {value!r} (es. DOC).")
    return key
