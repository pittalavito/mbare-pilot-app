"""search_context: the tool the Refiner (and the chatbots that want it) use on the project's context index."""
from fakes import as_dict
from models.domain.agent import RunOrigin
from models.domain.project import Project, ProjectSource
from service.rag_service import RagService
from tool.context import ToolContext
from tool.list.project.search_context import SEARCH_CONTEXT


def test_the_tool_gives_the_best_pieces_with_their_source(project_store, project_data_service, masking_service, rag_store):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    rag = RagService(project_data_service, masking_service, project_store, rag_store)
    run = ToolContext(project_name="acme", git=None, origin=RunOrigin.CHAT, rag=rag)  # type: ignore[arg-type]
    search = SEARCH_CONTEXT.build(run).func

    assert "vuoto o non indicizzato" in as_dict(search(question="Che database usiamo?"))["error"]
    project_data_service.save_context("acme", "db", "# Database\n\n## Scelta\nPostgreSQL 16, uno schema per modulo.")
    rag.reindex("acme")

    [hit] = as_dict(search(question="Che database usiamo?"))["hits"]
    assert (hit["path"], hit["title"], hit["section"]) == ("context/db.md", "Database", "Scelta")
    assert "vuota" in as_dict(search(question=" "))["error"]
    assert "contesto del progetto" in as_dict(SEARCH_CONTEXT.build(ToolContext(project_name="acme", git=None)).func(question="x"))["error"]  # type: ignore[arg-type]
