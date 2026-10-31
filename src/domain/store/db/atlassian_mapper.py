"""Atlassian: a project's settings and favourites <-> ``project_atlassian`` /
``atlassian_favorite`` rows. The token goes in and out already encrypted /
decrypted by AtlassianStore: the mapper never sees the key."""
from domain.store.db.mapper import as_utc
from models.domain.atlassian import AtlassianFavorite, AtlassianSettings, FavoriteKind
from models.store.db import AtlassianFavoriteTable, ProjectAtlassianTable


class Adapter:
    """Read seam: DB rows -> domain models."""

    @staticmethod
    def to_atlassian_settings(row: ProjectAtlassianTable, api_token: str) -> AtlassianSettings:
        """``api_token`` is the decrypted ``row.api_token``."""
        return AtlassianSettings.model_validate({**row.model_dump(), "api_token": api_token})

    @staticmethod
    def to_atlassian_favorite(row: AtlassianFavoriteTable) -> AtlassianFavorite:
        favorite = AtlassianFavorite.model_validate({**row.model_dump(), "kind": FavoriteKind(row.kind)})
        favorite.created_at = as_utc(favorite.created_at)
        return favorite


class Factory:
    """Write seam: domain models -> DB rows."""

    @staticmethod
    def to_atlassian_row(settings: AtlassianSettings, encrypted_token: str) -> ProjectAtlassianTable:
        return ProjectAtlassianTable(
            project_name=settings.project_name,
            base_url=settings.base_url,
            email=settings.email,
            api_token=encrypted_token,
            jira_project_key=settings.jira_project_key,
            confluence_space_key=settings.confluence_space_key,
        )

    @staticmethod
    def to_atlassian_favorite_row(favorite: AtlassianFavorite) -> AtlassianFavoriteTable:
        return AtlassianFavoriteTable(**{**favorite.model_dump(), "kind": favorite.kind.value})
