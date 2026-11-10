"""The context index: domain ``RagDocument``, ``RagPiece`` <-> ``document`` / ``chunk`` rows."""
from domain.store.db.mapper import as_utc
from models.domain.rag import RagDocument, RagPiece, RagSource
from models.store.db import ChunkTable, DocumentTable


class Adapter:
    """Read seam: DB rows -> domain models."""

    @staticmethod
    def to_rag_document(row: DocumentTable) -> RagDocument:
        return RagDocument(id=row.id, project_name=row.project_name, path=row.path, source=RagSource(row.source), title=row.title,
                           content_hash=row.content_hash, **({"indexed_at": as_utc(row.indexed_at)} if row.indexed_at else {}))

    @staticmethod
    def to_rag_piece(row: ChunkTable) -> RagPiece:
        return RagPiece(position=row.position, section=row.section, text=row.text, embedding_model=row.embedding_model,
                        embedding=[float(value) for value in row.embedding])


class Factory:
    """Write seam: domain models -> DB rows."""

    @staticmethod
    def to_document_row(document: RagDocument) -> DocumentTable:
        return DocumentTable(id=document.id, project_name=document.project_name, path=document.path, source=document.source.value,
                             title=document.title, content_hash=document.content_hash, indexed_at=document.indexed_at)

    @staticmethod
    def to_chunk_row(project_name: str, piece: RagPiece) -> ChunkTable:
        return ChunkTable(document_id=0, project_name=project_name, position=piece.position, section=piece.section, text=piece.text,
                          embedding_model=piece.embedding_model, embedding=piece.embedding)
