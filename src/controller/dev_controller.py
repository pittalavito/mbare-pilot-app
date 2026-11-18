"""The tests' settings (blocco 09) and the Operator's commands (plan 11), under
/projects/{project}: the tests' settings, the allowed commands, the project's
Operator (Dev), the commands waiting for the user's ok and one command run by hand («✋ A mano», plan 25)."""
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from controller.dependencies import command_service, dev_checks_service
from models.domain.dev import DevSettings, TestScope
from models.domain.project import CommandRequest
from service.command_service import CommandService
from service.dev_checks_service import DevChecksService

router = APIRouter(prefix="/projects/{project}", tags=["dev"])


class DevSettingsResponse(DevSettings):
    allowed_commands: list[str]
    """The commands the Operator may run."""
    suggested_commands: list[str]
    """The detected install and test commands not allowed yet: offered with a click."""
    operator_chatbot_id: int | None
    """The project's Operator (Dev, for the pre/post development tasks); None = the project's first one."""


class DevSettingsRequest(BaseModel):
    test_scope: TestScope = TestScope.ALL
    commands: dict[str, str] = {}
    """Repository folder → the tests' command; empty or missing = the detected one."""
    allowed_commands: list[str] | None = None
    """None = unchanged."""
    operator_chatbot_id: int | None = None


class CommandAnswer(BaseModel):
    command: str
    allow: bool
    """False = «No»: the request is dropped."""
    always: bool = False
    """With ``allow``: «Sempre» (added to the list) instead of «Solo stavolta»."""


class CommandRunRequest(BaseModel):
    repository: str = ""
    command: str


class CommandRunResponse(BaseModel):
    allowed: bool
    """False: not run, a request waits for the user's answer."""
    exit_code: int | None = None
    output: str = ""


def _response(project: str, service: DevChecksService, commands: CommandService, settings: DevSettings) -> DevSettingsResponse:
    return DevSettingsResponse(**settings.model_dump(), allowed_commands=commands.allowed(project),
                               suggested_commands=commands.suggested(project), operator_chatbot_id=service.operator_chatbot_id(project))


@router.get("/dev-settings")
def dev_settings(project: str, service: DevChecksService = Depends(dev_checks_service),
                 commands: CommandService = Depends(command_service)) -> DevSettingsResponse:
    """Each repository's tests (tool, detected command, the one written), the default scope, the commands."""
    return _response(project, service, commands, service.settings(project))


@router.put("/dev-settings")
def save_dev_settings(project: str, request: DevSettingsRequest, service: DevChecksService = Depends(dev_checks_service),
                      commands: CommandService = Depends(command_service)) -> DevSettingsResponse:
    if request.allowed_commands is not None:
        commands.save_allowed(project, request.allowed_commands)
    service.save_operator(project, request.operator_chatbot_id)
    return _response(project, service, commands, service.save_settings(project, request.test_scope, request.commands))


@router.get("/command-requests")
def command_requests(project: str, commands: CommandService = Depends(command_service)) -> list[CommandRequest]:
    """The commands the Operator asked for, waiting for an answer (the agent panel shows them)."""
    return commands.requests(project)


@router.post("/command-requests/answer", status_code=status.HTTP_204_NO_CONTENT)
def answer_command_request(project: str, answer: CommandAnswer, commands: CommandService = Depends(command_service)) -> Response:
    commands.answer(project, answer.command, allow=answer.allow, always=answer.always)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/commands/run")
def run_command(project: str, request: CommandRunRequest, commands: CommandService = Depends(command_service)) -> CommandRunResponse:
    """«✋ A mano» (plan 25): one command in a repository of the project, if allowed (or granted once);
    else it becomes a request and nothing runs."""
    outcome = commands.run(project, request.repository, request.command)
    return CommandRunResponse(allowed=outcome.allowed, exit_code=outcome.exit_code, output=outcome.output)
