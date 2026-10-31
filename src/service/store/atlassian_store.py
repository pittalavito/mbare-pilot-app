"""A project's Atlassian connection (site, account, API token, Jira project
and Confluence space) and its favourite issues and pages. The token is
encrypted at rest with the app's SecretBox: the store encrypts and decrypts
it, so the services only ever see it in clear."""
from sqlalchemy.engine import Engine

from core.observability import LogPrefix, log_warning
from core.secret_box import SecretBox
from domain.store.db.atlassian_favorite_repository import DbAtlassianFavoriteRepository
from domain.store.db.atlassian_mapper import Adapter, Factory
from domain.store.db.atlassian_repository import DbAtlassianRepository
from models.domain.atlassian import AtlassianFavorite, AtlassianSettings, FavoriteKind


class AtlassianStore:

    def __init__(self, engine: Engine, secret_box: SecretBox):
        self._settings = DbAtlassianRepository(engine)
        self._favorites = DbAtlassianFavoriteRepository(engine)
        self._secret_box = secret_box

    def get_settings(self, project_name: str) -> AtlassianSettings | None:
        """The API token comes back decrypted; empty when it cannot be (key
        changed or missing), so the project shows as not configured."""
        row = self._settings.get(project_name)
        if row is None:
            return None
        token = self._secret_box.decrypt(row.api_token) if self._secret_box.is_configured else None
        if token is None:
            log_warning(LogPrefix.ATLASSIAN_STORE, "Token Atlassian di %s non decifrabile", project_name)
        return Adapter.to_atlassian_settings(row, api_token=token or "")

    def save_settings(self, settings: AtlassianSettings) -> AtlassianSettings:
        """The API token is saved encrypted."""
        encrypted = self._secret_box.encrypt(settings.api_token.get_secret_value())
        self._settings.save(Factory.to_atlassian_row(settings, encrypted_token=encrypted))
        return settings

    def delete_settings(self, project_name: str) -> bool:
        return self._settings.delete(project_name)

    def list_favorites(self, project_name: str) -> list[AtlassianFavorite]:
        return [Adapter.to_atlassian_favorite(row) for row in self._favorites.list_for_project(project_name)]

    def find_favorite(self, project_name: str, kind: FavoriteKind, ref: str) -> AtlassianFavorite | None:
        row = self._favorites.find(project_name, kind.value, ref)
        return Adapter.to_atlassian_favorite(row) if row else None

    def get_favorite(self, favorite_id: int) -> AtlassianFavorite | None:
        row = self._favorites.get(favorite_id)
        return Adapter.to_atlassian_favorite(row) if row else None

    def save_favorite(self, favorite: AtlassianFavorite) -> AtlassianFavorite:
        row = self._favorites.save(Factory.to_atlassian_favorite_row(favorite))
        return Adapter.to_atlassian_favorite(row)

    def delete_favorite(self, favorite_id: int) -> bool:
        return self._favorites.delete(favorite_id)

    def delete_favorites_of_other_sites(self, project_name: str, site: str) -> int:
        return self._favorites.delete_other_sites(project_name, site)
