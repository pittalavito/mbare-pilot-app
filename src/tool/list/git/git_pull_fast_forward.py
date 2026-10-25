"""git_pull_fast_forward: bring a repository of the run's project up to date
with its upstream, only by fast-forward (never a merge). Refused with local
uncommitted changes, a detached HEAD or no upstream; the authors of the
commits that arrive are registered as sensitive (masked for the LLM)."""
from datapizza.tools import Tool, tool

from core.error import AppError
from models.domain.masking import MaskCategory
from models.domain.tool import GitPullResponse
from tool.context import ToolContext
from tool.list.git.errors import git_error
from tool.list.git.params import Repository
from tool.spec import ToolSpec


def build(context: ToolContext) -> Tool:

    @tool(name="git_pull_fast_forward")
    def git_pull_fast_forward(repository: Repository) -> str:
        """Update a git repository of the current project from its remote
        (git pull --ff-only): only when no merge is needed. Refused if the
        repository has uncommitted changes to tracked files, a detached HEAD or
        no upstream. Returns the commits that arrived."""
        try:
            result = context.git.pull_fast_forward(context.require_project(), repository)
        except AppError as exc:
            return git_error(context, exc)
        
        context.register_sensitive(MaskCategory.REPOSITORY, repository)
        
        for commit in result.commits:
            context.register_sensitive(MaskCategory.PERSON, commit.author)
            context.register_sensitive(MaskCategory.EMAIL, commit.email)
        
        response = GitPullResponse(
            repository=repository, 
            branch=result.branch, 
            upstream=result.upstream,
            updated=not result.up_to_date, 
            commits=result.commits,
        )
        
        return response.model_dump_json()

    return git_pull_fast_forward


GIT_PULL_FAST_FORWARD = ToolSpec(
    name="git_pull_fast_forward",
    description="Aggiorna un repository del progetto dal remoto solo in fast-forward (mai merge); rifiuta con modifiche locali non committate.",
    build=build,
)
