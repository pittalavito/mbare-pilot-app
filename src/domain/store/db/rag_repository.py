"""The projects' context index (tables document and chunk)."""
from sqlalchemy.engine import Engine
from sqlmodel import col, delete, func, select

from domain.store.db.repository import SqlRepository
from models.store.db import ChunkTable, DocumentTable


class DbRagRepository(SqlRepository[DocumentTable]):

    def __init__(self, engine: Engine):
        super().__init__(engine, DocumentTable)

    def find(self, project_name: str, path: str) -> DocumentTable | None:
        statement = select(DocumentTable).where(DocumentTable.project_name == project_name, DocumentTable.path == path)
        with self._session() as session:
            return session.exec(statement).first()

    def list_for_project(self, project_name: str) -> list[DocumentTable]:
        statement = select(DocumentTable).where(DocumentTable.project_name == project_name).order_by(col(DocumentTable.path))
        with self._session() as session:
            return list(session.exec(statement).all())

    def replace(self, document: DocumentTable, chunks: list[ChunkTable]) -> DocumentTable:
        """The document (new or updated) with exactly ``chunks``, in one transaction."""
        with self._session() as session:
            saved = session.merge(document)
            session.flush()
            session.exec(delete(ChunkTable).where(col(ChunkTable.document_id) == saved.id))
            for chunk in chunks:
                session.add(ChunkTable(**{**chunk.model_dump(exclude={"id", "document_id"}), "document_id": saved.id}))
            session.commit()
            session.refresh(saved)
            return saved

    def remove(self, project_name: str, path: str) -> bool:
        """The document and its pieces; False when it was not indexed."""
        with self._session() as session:
            row = session.exec(select(DocumentTable).where(DocumentTable.project_name == project_name, DocumentTable.path == path)).first()
            if row is None:
                return False
            session.exec(delete(ChunkTable).where(col(ChunkTable.document_id) == row.id))
            session.delete(row)
            session.commit()
            return True

    def chunks(self, project_name: str, embedding_model: str) -> list[tuple[ChunkTable, DocumentTable]]:
        """Every piece of the project made by ``embedding_model``, with its document."""
        statement = (
            select(ChunkTable, DocumentTable).join(DocumentTable, col(DocumentTable.id) == col(ChunkTable.document_id))
            .where(ChunkTable.project_name == project_name, ChunkTable.embedding_model == embedding_model)
            .order_by(col(DocumentTable.path), col(ChunkTable.position))
        )
        with self._session() as session:
            return [(chunk, document) for chunk, document in session.exec(statement).all()]

    def count_chunks(self, project_name: str) -> int:
        with self._session() as session:
            return session.exec(select(func.count()).select_from(ChunkTable).where(ChunkTable.project_name == project_name)).one()
