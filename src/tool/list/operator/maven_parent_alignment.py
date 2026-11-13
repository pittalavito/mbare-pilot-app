"""maven_parent_alignment (the Operator, plan 11): the project's root POMs
compared with the version of the parent POM (recognised by itself), as the
function of the same name: the ones to align first. Reads only."""
from typing import Annotated

from datapizza.tools import Tool, tool

from core.error import AppError
from function.list.maven_parent_alignment import alignment_text
from models.domain.tool import PomAlignmentResponse, ToolErrorResponse
from service.maven_service import MavenService
from tool.context import ToolContext
from tool.list.git.errors import git_error
from tool.spec import ToolSpec

ParentArtifactId = Annotated[str, "artifactId of the parent POM; '' = recognised (the repository the others name as <parent>)."]
Property = Annotated[str, "Microservices' property with the libraries' version, a name or a pattern with * (e.g. '*.lib.version'); '' = libraries only."]


def build(context: ToolContext) -> Tool:

    @tool(name="maven_parent_alignment")
    def maven_parent_alignment(parent_artifact_id: ParentArtifactId, property: Property) -> PomAlignmentResponse | ToolErrorResponse:
        """Compare the root pom.xml of every repository of the current project
        with the version of the parent POM: first the ones to align (current and
        expected version), then the aligned ones. Reads only."""
        try:
            alignment = MavenService(context.git).parent_alignment(context.require_project(), parent_artifact_id, property)
        except AppError as exc:
            return git_error(context, exc)
        return PomAlignmentResponse(text=alignment_text(alignment), alignment=alignment)

    return maven_parent_alignment


MAVEN_PARENT_ALIGNMENT = ToolSpec(
    name="maven_parent_alignment",
    description="Confronta i pom.xml dei repository con la versione del POM parent: prima quelli da allineare (solo lettura).",
    build=build,
)
