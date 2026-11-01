"""What a function step can use while a pipeline runs: the project, the run
input and the services. Built by PipelineRunner for every function step."""
from dataclasses import dataclass

from service.git_service import GitService
from service.maven_service import MavenService
from service.project_data_service import ProjectDataService


@dataclass(frozen=True)
class FunctionContext:
    project_name: str
    """The pipeline's project: functions only work on it."""
    pipeline_input: str
    """The run input ({pipeline_input}); the step input is passed to the function separately."""
    git: GitService
    project_data: ProjectDataService

    @property
    def maven(self) -> MavenService:
        """The POMs of the project's repositories (stateless, built on ``git``)."""
        return MavenService(self.git)
