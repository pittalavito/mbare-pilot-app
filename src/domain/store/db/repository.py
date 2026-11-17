"""SQL persistence base for the DB store: the ``Engine`` factory, the
``SqlRepository`` base every concrete repository extends and ``transaction``
(unit of work across repositories). Concrete repositories live in their own
files under domain/store/db/.

No migrations, no backward compatibility: ``create_all`` creates the missing
tables at startup; a table whose columns changed in code is recreated only
while it is empty (with the tables referencing it); with rows the app stops and
says to delete the database.
"""
import json
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Generic, TypeVar

from sqlalchemy import func, inspect, text
from sqlalchemy.engine import Engine as SqlAlchemyEngine
from sqlalchemy.orm import class_mapper
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.sql.expression import SelectOfScalar

# Imported for its side effect: registers every table on SQLModel.metadata.
import models.store.db  # noqa: F401
from core.observability import LogPrefix, log_warning

TableT = TypeVar("TableT", bound=SQLModel)

class _TransactionSession(Session):
    """The Session of an open ``transaction``: the repositories' ``commit`` only
    flushes and leaving their ``with`` block keeps it open; ``transaction``
    commits once at the end."""

    def commit(self) -> None:
        self.flush()

    def __exit__(self, type_: Any, value: Any, traceback: Any) -> None:
        pass


_current_transaction: ContextVar[_TransactionSession | None] = ContextVar("db_transaction", default=None)


@contextmanager
def transaction(engine: SqlAlchemyEngine) -> Iterator[None]:
    """Unit of work: the repository calls inside the block share one Session
    and are committed together at the end, or rolled back together when the
    block raises. A block opened inside another joins the outer one."""
    if _current_transaction.get() is not None:
        yield
        return
    # Rows returned inside the block stay readable after the final commit.
    session = _TransactionSession(engine, expire_on_commit=False)
    token = _current_transaction.set(session)
    try:
        yield
        Session.commit(session)
    except BaseException:
        session.rollback()
        raise
    finally:
        _current_transaction.reset(token)
        session.close()


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
                    "contiene dati: cancella il database e riavvia."
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
        """A new Session bound to the engine, or the open ``transaction``'s:
        ``with self._session() as session:``."""
        current = _current_transaction.get()
        if current is not None and current.get_bind() is self._engine:
            return current
        return Session(self._engine)

    def _grouped(self, statement: SelectOfScalar[TableT], ids: list[int], key: Callable[[TableT], int]) -> dict[int, list[TableT]]:
        """The rows of ``statement`` grouped by ``key``, every id of ``ids`` present
        (an empty list when it has no rows); no query when ``ids`` is empty."""
        grouped: dict[int, list[TableT]] = {id_: [] for id_ in ids}
        if ids:
            with self._session() as session:
                for row in session.exec(statement):
                    grouped[key(row)].append(row)
        return grouped

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
        mapper = class_mapper(self._table)
        pk_names = [mapper.get_property_by_column(column).key for column in mapper.primary_key]
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
