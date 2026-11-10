"""The projects' context index (Postgres, pgvector): documents and their pieces."""
from sqlalchemy.engine import Engine

from domain.store.db.rag_mapper import Adapter, Factory
from domain.store.db.rag_repository import DbRagRepository
from models.domain.rag import RagDocument, RagPiece


class RagStore:

    def __init__(self, engine: Engine):
        self._index = DbRagRepository(engine)

    def get_document(self, project_name: str, path: str) -> RagDocument | None:
        row = self._index.find(project_name, path)
        return Adapter.to_rag_document(row) if row else None

    def list_documents(self, project_name: str) -> list[RagDocument]:
        """By path."""
        return [Adapter.to_rag_document(row) for row in self._index.list_for_project(project_name)]

    def save_document(self, document: RagDocument, pieces: list[RagPiece]) -> RagDocument:
        """The document with exactly ``pieces`` (the old ones replaced), in one transaction."""
        current = self._index.find(document.project_name, document.path)
        row = Factory.to_document_row(document.model_copy(update={"id": current.id if current else None}))
        saved = self._index.replace(row, [Factory.to_chunk_row(document.project_name, piece) for piece in pieces])
        return Adapter.to_rag_document(saved)

    def remove_document(self, project_name: str, path: str) -> bool:
        return self._index.remove(project_name, path)

    def pieces(self, project_name: str, embedding_model: str) -> list[tuple[RagPiece, RagDocument]]:
        """Every piece of the project made by ``embedding_model``, with its document, by path and position."""
        return [(Adapter.to_rag_piece(chunk), Adapter.to_rag_document(document))
                for chunk, document in self._index.chunks(project_name, embedding_model)]

    def count_pieces(self, project_name: str) -> int:
        return self._index.count_chunks(project_name)
