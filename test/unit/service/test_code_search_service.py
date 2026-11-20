"""Plan 23: the free search in the project's code and its code reference."""
import shutil
import subprocess
from datetime import datetime

import pytest

from core.error import ConflictError, NotFoundError, ValidationError
from domain.project import code_search
from models.domain.code_search import CodeQuery
from models.domain.note import AgentTask, NoteType, Reference
from models.domain.project import Project, ProjectSource
from service.code_search_service import MAX_FILE_BYTES, CodeSearchService

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


@pytest.fixture
def service(tmp_path, project_store, git_service, project_data_service) -> CodeSearchService:
    """Project «acme» with repositories ``api`` and ``web``."""
    for name, files in {
        "api": {"src/Order.java": "class Order {}\n  @Deprecated void old() {}\n", "README.md": "Order service\n",
                ".gitignore": "build/\n", "build/Gen.java": "@Deprecated\n",
                "logo.bin": b"@Deprecated\0\0", "latin.txt": "@Deprecated \xe8".encode("latin-1")},
        "web": {"app.ts": "// @deprecated old\nconst order = 1;\n"},
    }.items():
        repo = tmp_path / "acme" / name
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
        for path, content in files.items():
            (repo / path).parent.mkdir(parents=True, exist_ok=True)
            (repo / path).write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path=str(tmp_path / "acme")))
    return CodeSearchService(git_service, project_data_service, clock=lambda: datetime(2026, 11, 18, 9, 30))


def _found(result):
    return [(match.path, match.line, match.text) for match in result.matches]


def test_plain_text_skips_ignored_binary_and_non_utf8(service):
    result = service.search("acme", CodeQuery(query="@Deprecated"))

    assert _found(result) == [("api/src/Order.java", 2, "@Deprecated void old() {}")]
    assert (result.total, result.files, result.truncated) == (1, 1, False)


def test_regex_files_and_repository_filters(service):
    assert {m.path for m in service.search("acme", CodeQuery(query=r"(?i)@deprecated", regex=True)).matches} == {
        "api/src/Order.java", "web/app.ts"}
    assert _found(service.search("acme", CodeQuery(query="Order", files="*.java"))) == [("api/src/Order.java", 1, "class Order {}")]
    assert _found(service.search("acme", CodeQuery(query="Order", files="src/**"))) == [("api/src/Order.java", 1, "class Order {}")]
    assert _found(service.search("acme", CodeQuery(query="order", repository="web"))) == [("web/app.ts", 2, "const order = 1;")]
    with pytest.raises(NotFoundError):
        service.search("acme", CodeQuery(query="x", repository="nope"))
    with pytest.raises(ValidationError, match="Regex non valida"):
        service.search("acme", CodeQuery(query="(", regex=True))


def test_limit_and_short_lines(service, tmp_path):
    (tmp_path / "acme" / "web" / "long.ts").write_text("x" * 300 + " order\n" + "order\n" * 3, encoding="utf-8")
    (tmp_path / "acme" / "web" / "big.ts").write_text("order\n" * (MAX_FILE_BYTES // 6 + 1), encoding="utf-8")

    result = service.search("acme", CodeQuery(query="order", repository="web"), limit=2, chars=20)

    assert len(result.matches) == 2 and result.total == 5 and result.files == 2 and result.truncated
    assert all(len(match.text) <= 21 for match in result.matches)


def test_the_search_saved_as_a_reference_rewritten_and_linked(service, project_data_service):
    task = project_data_service.create_agent_task("acme", AgentTask(title="Login"))
    saved = service.save("acme", CodeQuery(query="@Deprecated"), link_to=[task])

    assert (saved.note, saved.created, saved.total) == ("code-reference-deprecated.md", True, 1)
    kind, reference = project_data_service.reference("acme", saved.note)
    assert kind is NoteType.CODE_REFERENCE and reference.source == code_search.SOURCE and reference.title == "@Deprecated"
    assert "Ricerca: «@Deprecated» · 18/11/2026 09:30" in reference.content
    assert "- `api/src/Order.java:2` → @Deprecated void old() {}" in reference.content
    assert service.save("acme", CodeQuery(query="@Deprecated")).created is False


def test_nothing_found_and_a_reference_written_by_hand(service, project_data_service):
    saved = service.save("acme", CodeQuery(query="nessuno"), title="Vuota")
    assert "Nessun risultato." in project_data_service.reference("acme", saved.note)[1].content

    project_data_service.create_reference("acme", NoteType.CODE_REFERENCE, Reference(title="Mia", content="mio"))
    with pytest.raises(ConflictError):
        service.save("acme", CodeQuery(query="Order"), title="Mia")


def test_the_reference_says_how_many_are_left_out():
    query = CodeQuery(query="x", regex=True, files="*.py", repository="api")
    text = code_search.reference("T", query, [], 3, datetime(2026, 1, 2, 3, 4)).content
    assert "regex" in code_search.describe(query) and "*.py" in code_search.describe(query) and "api" in code_search.describe(query)
    assert "… e altri 3 risultati" in text
