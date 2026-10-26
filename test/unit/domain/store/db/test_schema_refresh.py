"""Tables whose columns changed in code are recreated at startup only while empty."""
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from domain.store.db.repository import Engine


@pytest.fixture
def outdated():
    """A database where ``conversation`` has an extra column the code no longer has."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE conversation ADD COLUMN legacy TEXT"))
    return engine


def _columns(engine, table):
    return {column["name"] for column in inspect(engine).get_columns(table)}


def test_empty_outdated_table_is_recreated_with_its_dependents(outdated):
    with outdated.begin() as connection:
        connection.execute(text("INSERT INTO project (name, description, source, root_path, embedding_model, created_at) "
                                "VALUES ('p', '', 'folder', '/p', 'x', CURRENT_TIMESTAMP)"))

    Engine._drop_outdated_empty_tables(outdated)
    SQLModel.metadata.create_all(outdated)

    assert "legacy" not in _columns(outdated, "conversation")
    with outdated.connect() as connection:  # unrelated tables keep their rows
        assert connection.execute(text("SELECT count(*) FROM project")).scalar() == 1


def test_outdated_table_with_rows_stops_the_app(outdated):
    with outdated.begin() as connection:
        connection.execute(text("INSERT INTO conversation (chatbot_id, title, created_at, updated_at, legacy) "
                                "VALUES (1, 't', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'x')"))

    with pytest.raises(RuntimeError, match="conversation"):
        Engine._drop_outdated_empty_tables(outdated)
    assert "legacy" in _columns(outdated, "conversation")


def test_a_new_column_with_a_default_is_added_and_rows_are_kept():
    """``copilot_session`` as it was before ``model`` and ``prompt`` existed, with a row."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO project (name, description, source, root_path, embedding_model, created_at) "
                                "VALUES ('p', '', 'folder', '/p', 'x', CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO copilot_session (project_name, task_note, repository, copilot_session_id, status, "
                                "cancel_requested, changed_files, premium_requests, created_at, updated_at, model, prompt) "
                                "VALUES ('p', 't.md', '', 'u1', 'done', 0, '[]', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'x', 'y')"))
        connection.execute(text("ALTER TABLE copilot_session DROP COLUMN model"))
        connection.execute(text("ALTER TABLE copilot_session DROP COLUMN prompt"))

    Engine._add_missing_columns(engine)
    Engine._drop_outdated_empty_tables(engine)  # nothing left to recreate

    with engine.connect() as connection:
        assert connection.execute(text("SELECT task_note, model, prompt FROM copilot_session")).one() == ("t.md", "", "")


def test_up_to_date_schema_is_left_alone(outdated):
    with outdated.begin() as connection:
        connection.execute(text("ALTER TABLE conversation DROP COLUMN legacy"))
        connection.execute(text("INSERT INTO conversation (chatbot_id, title, created_at, updated_at) "
                                "VALUES (1, 't', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))

    Engine._drop_outdated_empty_tables(outdated)

    with outdated.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM conversation")).scalar() == 1
