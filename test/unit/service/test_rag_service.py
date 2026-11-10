"""The context index (RAG): pieces by heading, masking before an embedder
that is not local, documents reindexed only when changed, the hybrid
search, the done activities with «Imparato», and hit@5 on the data set."""
from pathlib import Path

import pytest

from core.error import NotFoundError, ValidationError
from domain.client.embedding.embedder import Embedder, HashingEmbedder
from domain.rag.chunking import split_markdown, title_of
from models.domain.chat import EmbeddingModelName
from models.domain.masking import MaskCategory
from models.domain.note import Activity, ActivityStatus
from models.domain.project import Project, ProjectSource
from service.rag_service import KEYWORD_BONUS, RagService

DATA = Path(__file__).parents[3] / "resource" / "eval" / "rag"


class RemoteEmbedder(Embedder):
    """A non-local embedder: remembers every text it was sent."""

    def __init__(self):
        self.sent: list[str] = []
        self._inner = HashingEmbedder()

    @property
    def name(self) -> str:
        return "remoto-finto"

    @property
    def local(self) -> bool:
        return False

    def embed(self, text: str) -> list[float]:
        self.sent.append(text)
        return self._inner.embed(text)


@pytest.fixture
def rag(project_store, project_data_service, masking_service, rag_store) -> RagService:
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    return RagService(project_data_service, masking_service, project_store, rag_store)


@pytest.fixture
def data(project_data_service):
    return project_data_service


def _load_corpus(data) -> None:
    for path in sorted((DATA / "context").glob("*.md")):
        data.save_context("acme", path.name, path.read_text(encoding="utf-8"))


# --------------------------------------------------------------- chunking

def test_pieces_follow_the_headings_and_long_sections_are_split():
    text = "# Architettura\n\nIntro breve.\n\n## Backend\nFastAPI.\n\n## Vuota\n\n## Lunga\n" + "\n\n".join(" ".join(["parola"] * 120) for _ in range(3))

    pieces = split_markdown(text, title_of(text, "x"), max_words=300)

    assert [(piece.metadata["section"], len(piece.text.split())) for piece in pieces] == [("", 2), ("Backend", 1), ("Lunga", 240), ("Lunga", 120)]
    assert all(piece.metadata["title"] == "Architettura" for piece in pieces)
    assert [piece.metadata["position"] for piece in pieces] == [0, 1, 2, 3]
    assert title_of("niente titolo", "riserva") == "riserva"


def test_a_paragraph_too_long_is_split_on_sentences_then_words():
    sentence = " ".join(["x"] * 40) + "."
    pieces = split_markdown("## S\n" + " ".join([sentence] * 3) + " " + " ".join(["y"] * 90), "T", max_words=50)

    assert [len(piece.text.split()) for piece in pieces] == [40, 40, 40, 50, 40]
    assert split_markdown("", "T") == []


# --------------------------------------------------------------- indexing

def test_a_context_document_is_indexed_once_and_again_only_when_it_changes(rag, data, rag_store):
    data.save_context("acme", "architettura", "# Architettura\n\n## Backend\nFastAPI.\n\n## Database\nPostgres.")

    assert rag.index_context("acme", "architettura.md") is True
    assert rag.index_context("acme", "architettura") is False  # unchanged: not embedded again
    [document] = rag_store.list_documents("acme")
    assert (document.path, document.source.value, document.title) == ("context/architettura.md", "context", "Architettura")
    assert [piece.section for piece, _ in rag_store.pieces("acme", "hashing-512")] == ["Backend", "Database"]

    data.save_context("acme", "architettura", "# Architettura\n\n## Backend\nDjango.")
    assert rag.index_context("acme", "architettura") is True
    assert [piece.text for piece, _ in rag_store.pieces("acme", "hashing-512")] == ["Django."]

    data.delete_context("acme", "architettura")
    assert rag.index_context("acme", "architettura") is False and rag_store.list_documents("acme") == []  # gone: out of the index


def test_text_is_masked_before_it_reaches_an_embedder_that_is_not_local(rag, data, masking_service, monkeypatch):
    remote = RemoteEmbedder()
    monkeypatch.setattr(rag, "embedder", lambda project: remote)
    masking_service.add_term("acme", MaskCategory.PERSON, "Marco Rossi")
    data.save_context("acme", "persone", "# Persone\n\n## Referenti\nMarco Rossi segue i pagamenti, scrivergli a marco@acme.it.")

    rag.index_context("acme", "persone")
    hits = rag.search("acme", "Chi segue i pagamenti, Marco Rossi?")

    assert remote.sent and all("Marco Rossi" not in text and "marco@acme.it" not in text for text in remote.sent)
    assert any("PERSONA_1" in text and "MAIL_1" in text for text in remote.sent)
    assert hits[0].text.startswith("Marco Rossi segue i pagamenti")  # the stored text stays in clear


def test_only_done_activities_with_imparato_are_indexed(rag, data, rag_store):
    name = data.create_activity("acme", Activity(title="Rilascio v2", description="La 2.0", learned="Le note prima del tag."))
    assert rag.index_activity("acme", name) is False  # not done yet
    data.save_activity("acme", name, data.activity("acme", name).model_copy(update={"status": ActivityStatus.DONE}))

    assert rag.index_activity("acme", name) is True
    pieces = rag_store.pieces("acme", "hashing-512")
    assert [(document.path, document.source.value, piece.section, piece.text) for piece, document in pieces] == [
        (f"notes/{name}", "activity", "", "La 2.0"), (f"notes/{name}", "activity", "Imparato", "Le note prima del tag."),
    ]  # title, description and «Imparato»: not the items

    data.save_activity("acme", name, data.activity("acme", name).model_copy(update={"learned": ""}))
    assert rag.index_activity("acme", name) is False and rag_store.list_documents("acme") == []
    data.delete_note("acme", name)
    assert rag.index_activity("acme", name) is False


def test_reindex_takes_everything_and_drops_what_is_gone(rag, data, rag_store):
    _load_corpus(data)
    data.create_activity("acme", Activity(title="Fatta", status=ActivityStatus.DONE, learned="Si impara."))
    data.create_activity("acme", Activity(title="Aperta", learned="Non ancora."))

    state = rag.reindex("acme")

    assert (state.documents, state.embedder, state.error) == (9, "hashing-512", None) and state.pieces > 20  # 8 documents, 1 activity
    data.delete_context("acme", "decisioni.md")  # deleted by hand, without the API
    assert rag.reindex("acme").documents == 8
    assert "context/decisioni.md" not in [document.path for document in rag_store.list_documents("acme")]


def test_the_embedder_of_a_project(rag, project_store, config):
    assert rag.embedder("acme").name == "hashing-512"  # RAG_EMBEDDER=hashing in the tests
    config.rag_embedder = ""
    assert rag.embedder("acme").name == "openrouter/openai/text-embedding-3-small"  # the project's model
    project_store.save(project_store.get("acme").model_copy(update={"embedding_model": EmbeddingModelName.OLLAMA_NOMIC_EMBED_TEXT}))
    with pytest.raises(ValidationError, match="non è ancora supportato"):
        rag.embedder("acme")
    assert "non è ancora supportato" in rag.state("acme").error
    with pytest.raises(NotFoundError):
        rag.embedder("manca")


def test_indexing_quietly_reports_instead_of_failing(rag, data, monkeypatch):
    data.save_context("acme", "doc", "# Doc\n\ntesto")

    def broken(project):
        raise ValidationError("OPENROUTER_API_KEY is not set")

    monkeypatch.setattr(rag, "embedder", broken)

    name = data.create_activity("acme", Activity(title="Fatta", status=ActivityStatus.DONE, learned="Qualcosa."))

    assert rag.index_quietly("acme", "context", "doc") == "OPENROUTER_API_KEY is not set"
    assert rag.index_quietly("acme", "activity", name) == "OPENROUTER_API_KEY is not set"
    assert rag.index_quietly("acme", "activity", "attivita-inesistente.md") is None  # nothing to index: no embedder needed


# ----------------------------------------------------------------- search

def test_the_search_cites_document_and_section_and_rewards_exact_words(rag, data):
    _load_corpus(data)
    rag.reindex("acme")

    [first, *rest] = rag.search("acme", "Cosa succede quando il consumer fallisce: dead letter queue?", limit=3)

    assert (first.path, first.title, first.section) == ("context/architettura.md", "Architettura", "Code e messaggi")
    assert "orders.dlq" in first.text and len(rest) == 2 and first.score >= rest[0].score
    with pytest.raises(ValidationError, match="vuota"):
        rag.search("acme", "  ")
    assert 0 < KEYWORD_BONUS < 1


def test_an_empty_index_finds_nothing(rag):
    assert rag.search("acme", "qualsiasi cosa") == []
