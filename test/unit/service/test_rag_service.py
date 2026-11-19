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


def test_reindex_takes_everything_and_drops_what_is_gone(rag, data, rag_store):
    _load_corpus(data)
    data.create_activity("acme", Activity(title="Fatta", status=ActivityStatus.DONE))  # activities are never indexed

    state = rag.reindex("acme")

    assert (state.documents, state.embedder, state.error) == (8, "hashing-512", None) and state.pieces > 20
    data.delete_context("acme", "decisioni.md")  # deleted by hand, without the API
    assert rag.reindex("acme").documents == 7
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

    assert rag.index_quietly("acme", "doc") == "OPENROUTER_API_KEY is not set"


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


# ------------------------------------------------------------ general context (plan 26)

@pytest.fixture
def general(project_store, project_data_service, masking_service, rag_store, tmp_path) -> RagService:
    from service.store.definition_store import DefinitionStore
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    definitions = DefinitionStore(tmp_path / "definition")
    definitions.save_definition("context/giro.md", "# Il giro\n\n## Avvia\nIl giro dei task si avvia con Avvia e lo esegue il worker.")
    definitions.save_definition("context/note.txt", "non un documento")
    return RagService(project_data_service, masking_service, project_store, rag_store, definitions)


def test_the_general_context_is_searched_in_every_project_and_the_project_wins(general, data, rag_store, monkeypatch):
    data.save_context("acme", "giro.md", "# Il giro\n\n## Avvia\nIl giro dei task si avvia con Avvia e lo esegue il worker.")
    general.index_context("acme", "giro.md")

    hits = general.search("acme", "come si avvia il giro dei task")
    assert [(hit.path, hit.origin) for hit in hits[:2]] == [("context/giro.md", "progetto"), ("general/giro.md", "generale")]
    assert hits[0].score == hits[1].score  # same text: the project first
    assert general.state("acme").general == 1 and general.state("acme").documents == 2
    assert [hit.origin for hit in general.search("acme", "giro", general=False)] == ["progetto"]  # Copilot

    calls = []
    monkeypatch.setattr(general, "_index", lambda *args: calls.append(args) or False)
    assert general.index_general("acme") == 0 and len(calls) == 1  # only the .md, unchanged


def test_a_general_document_gone_leaves_the_index_and_reindex_keeps_the_others(general, data, rag_store, tmp_path):
    general.reindex("acme")
    assert {document.path for document in rag_store.list_documents("acme")} == {"general/giro.md"}
    (tmp_path / "definition" / "context" / "giro.md").unlink()
    general.reindex("acme")
    assert rag_store.list_documents("acme") == []
    assert RagService(data, general._masking, general._projects, rag_store).general_documents() == []  # no definitions


def test_a_broken_general_index_does_not_stop_the_search(general, data, monkeypatch):
    from core.error import UpstreamError
    data.save_context("acme", "arch.md", "# Architettura\n\nFastAPI e React.")
    general.index_context("acme", "arch.md")
    monkeypatch.setattr(general, "index_general", lambda project: (_ for _ in ()).throw(UpstreamError("embedder giù")))
    assert [hit.path for hit in general.search("acme", "architettura")] == ["context/arch.md"]
