"""The projects' context index (RAG): what the Refiner and Copilot search
(tool ``search_context``) instead of reading everything.

**What is indexed**: the documents of the project's ``context/`` folder
(what an activity taught goes in ``context/imparato.md`` when it is closed)
and, in every project's index with its embedder, the **general context**:
the ``.md`` of the definitions' ``context/`` folder, how the app works
(plan 26), as ``general/<name>.md``. The general documents are (re)indexed
when a search or «Reindicizza» finds them changed (same ``content_hash`` =
nothing to embed); a project's piece wins over a general one at equal score.

**Indexing** (``index_context``, ``reindex``): the text is
split by heading (domain/rag/chunking.py, at most ``MAX_WORDS`` per piece),
each piece **masked** before it reaches an embedder that is not local (the
project's map plus automatic recognition, domain/masking/preview.py) and
embedded; document and pieces go in the ``document`` / ``chunk`` tables
(pgvector). A document whose text did not change (``content_hash``, same
embedder) is not embedded again. The stored text stays in clear: it is what
the searcher reads.

**Search** (``search``): the question is masked and embedded the same way;
every piece of the project made by the same embedder gets the cosine
similarity plus a bonus for the question's words it contains
(``KEYWORD_BONUS`` × the share of them found: technical names, acronyms);
the best ``limit`` come back with their document and section, to cite them.
The scoring runs in Python on the project's pieces (a context folder is
small): the same on Postgres and on the tests' SQLite.

**The embedder** of a project (``embedder``): ``RAG_EMBEDDER`` when set
(``hashing``: the offline mock), else the project's ``embedding_model``
through OpenRouter."""
import hashlib
import re
import unicodedata
from datetime import datetime, timezone

from config import Config
from core.error import AppError, NotFoundError, ValidationError
from core.observability import LogPrefix, log_exception, observed
from domain.client.embedding.embedder import Embedder, Factory, cosine_similarity
from domain.masking.preview import masked_text
from domain.project.data_paths import CONTEXT_DIR, note_file_name
from domain.rag.chunking import split_markdown, title_of
from models.domain.rag import RagDocument, RagHit, RagIndexState, RagPiece, RagSource
from service.masking_service import MaskingService
from service.project_data_service import ProjectDataService
from service.store.definition_store import DefinitionStore
from service.store.project_store import ProjectStore
from service.store.rag_store import RagStore

LIMIT = 5
GENERAL_DIR = "context"
"""The general context, in the definitions (``<data_home>/definition/context/*.md``)."""
GENERAL_PREFIX = "general/"
"""How the general documents are named in a project's index."""
KEYWORD_BONUS = 0.15
"""Added to the cosine when every word of the question is in the piece (a share of it for some)."""
_WORD = re.compile(r"[a-z0-9_]+")
_STOPWORDS = frozenset(
    "il lo la i gli le un uno una di del dello della dei degli delle a al allo alla ai agli alle da dal dalla in nel nella con su "
    "sul sulla per tra fra e ed o che chi come cosa quale quali dove quando perche non piu the and for how what".split()
)


class RagService:

    def __init__(self, project_data: ProjectDataService, masking: MaskingService, projects: ProjectStore, rag: RagStore,
                 definitions: DefinitionStore | None = None):
        self._data = project_data
        self._definitions = definitions
        self._masking = masking
        self._projects = projects
        self._rag = rag
        self._embedders: dict[str, Embedder] = {}

    # --------------------------------------------------------------- embedder
    def embedder(self, project_name: str) -> Embedder:
        """The project's embedder (cached by name). ValidationError when it cannot be built."""
        project = self._projects.get(project_name)
        if project is None:
            raise NotFoundError(f"Progetto non trovato: {project_name}")
        name = Config.get().rag_embedder.strip() or self._remote_name(project.embedding_model)
        if name not in self._embedders:
            self._embedders[name] = Factory.create(name)
        return self._embedders[name]

    @staticmethod
    def _remote_name(model: str) -> str:
        """``openai/text-embedding-3-small`` → ``openrouter/openai/text-embedding-3-small``."""
        if model.startswith("ollama/"):
            raise ValidationError(f"L'embedder {model} non è ancora supportato: usa openai/text-embedding-3-small o RAG_EMBEDDER=hashing.")
        return f"openrouter/{model}"

    def state(self, project_name: str) -> RagIndexState:
        """How many documents and pieces the index has, and with which embedder."""
        try:
            name, error = self.embedder(project_name).name, None
        except AppError as exc:
            name, error = "", str(exc)
        documents = self._rag.list_documents(project_name)
        return RagIndexState(documents=len(documents), pieces=self._rag.count_pieces(project_name), embedder=name, error=error,
                             general=sum(1 for document in documents if document.path.startswith(GENERAL_PREFIX)))

    # ---------------------------------------------------------------- general
    def general_documents(self) -> list[tuple[str, str]]:
        """The general context: ``(name, text)`` of each ``.md`` in the definitions' ``context/``, by name."""
        if self._definitions is None:
            return []
        found = []
        for path in sorted(self._definitions.list_definitions(GENERAL_DIR)):
            if path.endswith(".md") and (text := self._definitions.read_definition(path)) is not None:
                found.append((path.rsplit("/", 1)[-1], text))
        return found

    @observed(LogPrefix.RAG_SERVICE)
    def index_general(self, project_name: str) -> int:
        """The general documents in the project's index: the changed ones embedded, the gone ones removed. How many were embedded."""
        documents = self.general_documents()
        changed = sum(self._index(project_name, f"{GENERAL_PREFIX}{name}", RagSource.GENERAL, text, title_of(text, name.removesuffix(".md")))
                      for name, text in documents)
        wanted = {f"{GENERAL_PREFIX}{name}" for name, _ in documents}
        for document in self._rag.list_documents(project_name):
            if document.path.startswith(GENERAL_PREFIX) and document.path not in wanted:
                self._rag.remove_document(project_name, document.path)
        return changed

    # --------------------------------------------------------------- indexing
    @observed(LogPrefix.RAG_SERVICE)
    def index_context(self, project_name: str, name: str) -> bool:
        """One context document (re)indexed; False when it did not change.
        A document that no longer exists leaves the index."""
        path = f"{CONTEXT_DIR}/{note_file_name(name)}"
        try:
            text = self._data.read_context(project_name, name)
        except NotFoundError:
            self._rag.remove_document(project_name, path)
            return False
        return self._index(project_name, path, RagSource.CONTEXT, text, title_of(text, note_file_name(name).removesuffix(".md")))

    def remove_context(self, project_name: str, name: str) -> None:
        self._rag.remove_document(project_name, f"{CONTEXT_DIR}/{note_file_name(name)}")

    @observed(LogPrefix.RAG_SERVICE)
    def reindex(self, project_name: str) -> RagIndexState:
        """Every context document; what is indexed but no longer exists leaves
        the index. Unchanged documents are not embedded again."""
        self.embedder(project_name)  # an error here before touching anything
        wanted = {f"{CONTEXT_DIR}/{item.name}" for item in self._data.list_context(project_name)}
        for item in self._data.list_context(project_name):
            self.index_context(project_name, item.name)
        self.index_general(project_name)
        for document in self._rag.list_documents(project_name):
            if document.path not in wanted and not document.path.startswith(GENERAL_PREFIX):
                self._rag.remove_document(project_name, document.path)
        return self.state(project_name)

    def index_quietly(self, project_name: str, name: str) -> str | None:
        """``index_context`` without failing the caller (a save must not fail
        because the embedder is down): why it did not work, None when it did."""
        try:
            self.index_context(project_name, name)
            return None
        except AppError as exc:
            log_exception(LogPrefix.RAG_SERVICE, "Indicizzazione di %s non riuscita", name)
            return str(exc)

    def _index(self, project_name: str, path: str, source: RagSource, text: str, title: str) -> bool:
        embedder = self.embedder(project_name)
        digest = hashlib.sha256(f"{embedder.name}\n{text}".encode()).hexdigest()
        current = self._rag.get_document(project_name, path)
        if current is not None and current.content_hash == digest:
            return False
        pieces = []
        for chunk in split_markdown(text, title):
            section = str(chunk.metadata["section"])
            vector = embedder.embed(self._for_embedder(project_name, embedder, f"{title}\n{section}\n{chunk.text}"))
            pieces.append(RagPiece(position=int(chunk.metadata["position"]), section=section, text=chunk.text,
                                   embedding_model=embedder.name, embedding=vector))
        self._rag.save_document(RagDocument(project_name=project_name, path=path, source=source, title=title, content_hash=digest,
                                            indexed_at=datetime.now(timezone.utc)), pieces)
        return True

    def _for_embedder(self, project_name: str, embedder: Embedder, text: str) -> str:
        """``text`` as the embedder may see it: masked when it leaves the PC."""
        return text if embedder.local else masked_text(text, self._masking.entries(project_name)).text

    # ----------------------------------------------------------------- search
    def search(self, project_name: str, question: str, limit: int = LIMIT, general: bool = True) -> list[RagHit]:
        """The ``limit`` best pieces for ``question``: cosine similarity plus the keyword bonus, the project's
        first at equal score. ``general`` False = only the project's context (Copilot)."""
        if not question.strip():
            raise ValidationError("La domanda è vuota.")
        embedder = self.embedder(project_name)
        if general:
            try:
                self.index_general(project_name)
            except AppError:  # the project's pieces still answer
                log_exception(LogPrefix.RAG_SERVICE, "Contesto generale non indicizzato in %s", project_name)
        query = embedder.embed(self._for_embedder(project_name, embedder, question))
        words = keywords(question)
        hits = []
        for piece, document in self._rag.pieces(project_name, embedder.name):
            is_general = document.path.startswith(GENERAL_PREFIX)
            if is_general and not general:
                continue
            value = score(query, words, f"{document.title} {piece.section} {piece.text}", piece.embedding)
            hits.append(RagHit(path=document.path, title=document.title, section=piece.section, text=piece.text, score=round(value, 4),
                               origin="generale" if is_general else "progetto"))
        return sorted(hits, key=lambda hit: (hit.score, hit.origin == "progetto"), reverse=True)[:limit]


def _plain(text: str) -> str:
    """Lowercase, no accents."""
    return "".join(char for char in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(char))


def keywords(question: str) -> set[str]:
    """The words of a question that count for the bonus: at least 3 letters, not common, lowercase without accents."""
    return {word for word in _WORD.findall(_plain(question)) if len(word) >= 3 and word not in _STOPWORDS}


def score(query: list[float], words: set[str], text: str, embedding: list[float], bonus: float = KEYWORD_BONUS) -> float:
    """A piece's score for a question: cosine similarity plus ``bonus`` × the
    share of the question's ``words`` found in ``text`` (title, section, piece)."""
    found = set(_WORD.findall(_plain(text)))
    extra = bonus * len(words & found) / len(words) if words else 0.0
    return (cosine_similarity(query, embedding) if query and embedding else 0.0) + extra
