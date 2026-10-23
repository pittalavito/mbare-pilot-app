"""Files store facade: one import point for the local filesystem store. Unlike
the db/redis stores there is no Adapter/Factory — ``StoredFile`` is already the
domain shape, built directly by the repository."""
from domain.store.files.file_repository import LocalFileRepository
from models.store.files import StoredFile

__all__ = ["LocalFileRepository", "StoredFile"]
