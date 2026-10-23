"""SQL persistence base for the DB store: the ``Engine`` factory and the
``SqlRepository`` base every concrete repository extends. Concrete repositories
live in their own files under domain/store/db/.

Schema migrations are out of scope (no Alembic): ``create_all`` creates the
missing tables at startup. A table whose columns changed in code is recreated
only while it is empty (with the tables referencing it); with rows the app
stops and says which table to migrate by hand.
"""
import json
from typing import Any, Generic, Sequence, TypeVar

from sqlalchemy import func, inspect, text
from sqlalchemy.engine import Engine as SqlAlchemyEngine
from sqlmodel import Session, SQLModel, create_engine, select

from core.observability import LogPrefix, log_warning

# Imported for its side effect: registers every table on SQLModel.metadata.
import models.store.db  # noqa: F401

TableT = TypeVar("TableT", bound=SQLModel)


class Engine:

    @staticmethod
    def create_db_engine(db_url: str) -> SqlAlchemyEngine:
        """Create the engine from db_url and ensure the schema."""
        engine = create_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
            json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
        )
        if engine.dialect.name == "postgresql":
            # chunk.embedding is a pgvector column (image pgvector/pgvector).
            with engine.begin() as connection:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Engine._drop_outdated_empty_tables(engine)
        SQLModel.metadata.create_all(engine)
        return engine

    @staticmethod
    def _drop_outdated_empty_tables(engine: SqlAlchemyEngine) -> None:
        """Drop the existing tables whose columns differ from the code, plus the
        tables referencing them, so ``create_all`` recreates them. Only when all
        of them are empty: otherwise RuntimeError, nothing is dropped."""
        existing = set(inspect(engine).get_table_names())
        tables = [table for table in SQLModel.metadata.sorted_tables if table.name in existing]
        outdated = {
            table.name for table in tables
            if {column["name"] for column in inspect(engine).get_columns(table.name)} != set(table.columns.keys())
        }
        if not outdated:
            return
        for table in tables:  # parents come first: add whoever references a table to drop
            if any(key.column.table.name in outdated for key in table.foreign_keys):
                outdated.add(table.name)
        to_drop = [table for table in tables if table.name in outdated]
        with engine.begin() as connection:
            filled = [table.name for table in to_drop if connection.execute(select(func.count()).select_from(table)).scalar()]
            if filled:
                raise RuntimeError(
                    f"Lo schema di {', '.join(sorted(outdated))} è cambiato nel codice, ma {', '.join(filled)} "
                    "contiene dati: migrale a mano (o svuotale) e riavvia."
                )
            for table in reversed(to_drop):  # children first
                table.drop(connection)
        log_warning(LogPrefix.DB_ENGINE, "Tabelle ricreate col nuovo schema: %s", ", ".join(sorted(outdated)))


class SqlRepository(Generic[TableT]):
    """Common plumbing: one Session per operation, plus CRUD by primary key.
    Concrete repositories add their own queries, reusing ``_session()``.
    Everything is in terms of ``*Table`` rows."""

    def __init__(self, engine: SqlAlchemyEngine, table: type[TableT]):
        self._engine = engine
        self._table = table

    def _session(self) -> Session:
        """A new Session bound to the engine: ``with self._session() as session:``."""
        return Session(self._engine)

    def get(self, pk: Any) -> TableT | None:
        """Row by primary key, or None if absent."""
        with self._session() as session:
            return session.get(self._table, pk)

    def list(self) -> list[TableT]:
        """Every row."""
        with self._session() as session:
            return list(session.exec(select(self._table)).all())

    def save(self, row: TableT) -> TableT:
        """Insert or update one row, returning the persisted row."""
        with self._session() as session:
            row = session.merge(row)
            session.commit()
            session.refresh(row)
            return row

    def insert_missing(self, rows: Sequence[TableT]) -> int:
        """Insert the rows whose primary key is not in the table yet; existing
        rows are left untouched (seeds never overwrite edits). Returns the
        number of rows inserted."""
        pk_names = [column.key for column in self._table.__mapper__.primary_key]
        with self._session() as session:
            missing = []
            for row in rows:
                pk = tuple(getattr(row, name) for name in pk_names)
                if session.get(self._table, pk if len(pk) > 1 else pk[0]) is None:
                    missing.append(row)
            session.add_all(missing)
            session.commit()
            return len(missing)

    def delete(self, pk: Any) -> bool:
        """Remove one row by primary key. True if a row was deleted."""
        with self._session() as session:
            row = session.get(self._table, pk)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
