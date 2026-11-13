"""The checks around a development delegated to Copilot (blocco 09) and the
Operator's commands (plan 11), under /projects/{project}: the tests' settings,
whether the project has the two automations («Prepara sviluppo», «Verifica
sviluppo»), the allowed commands, the Operator of the preparation and the
commands waiting for the user's ok."""
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from controller.dependencies import command_service, dev_checks_service
from models.domain.dev import PREPARE_AUTOMATION, VERIFY_AUTOMATION, DevSettings, TestScope
from models.domain.project import CommandRequest
from service.command_service import CommandService
from service.dev_checks_service import DevChecksService

router = APIRouter(prefix="/projects/{project}", tags=["dev"])


class DevSettingsResponse(DevSettings):
    prepare_automation: bool
    """The project has «Prepara sviluppo» (switched on): the delegation offers to prepare the repositories."""
    verify_automation: bool
    """The project has «Verifica sviluppo» (switched on): it runs when a development goes «to verify»."""
    allowed_commands: list[str]
    """The commands the Operator may run."""
    suggested_commands: list[str]
    """The detected install and test commands not allowed yet: offered with a click."""
    operator_chatbot_id: int | None
    """The Operator of the preparation; None = the project's first one."""


class DevSettingsRequest(BaseModel):
    test_scope: TestScope = TestScope.ALL
    commands: dict[str, str] = {}
    """Repository folder → the tests' command; empty or missing = the detected one."""
    allowed_commands: list[str] | None = None
    """None = unchanged."""
    operator_chatbot_id: int | None = None
    auto_retries: int | None = Field(None, ge=0, le=3)
    """None = unchanged."""


class CommandAnswer(BaseModel):
    command: str
    allow: bool
    """False = «No»: the request is dropped."""
    always: bool = False
    """With ``allow``: «Sempre» (added to the list) instead of «Solo stavolta»."""


def _response(project: str, service: DevChecksService, commands: CommandService, settings: DevSettings) -> DevSettingsResponse:
    return DevSettingsResponse(**settings.model_dump(), prepare_automation=service.has(project, PREPARE_AUTOMATION),
                               verify_automation=service.has(project, VERIFY_AUTOMATION), allowed_commands=commands.allowed(project),
                               suggested_commands=commands.suggested(project), operator_chatbot_id=service.operator_chatbot_id(project))


@router.get("/dev-settings")
def dev_settings(project: str, service: DevChecksService = Depends(dev_checks_service),
                 commands: CommandService = Depends(command_service)) -> DevSettingsResponse:
    """Each repository's tests (tool, detected command, the one written), the default scope, the two automations, the commands."""
    return _response(project, service, commands, service.settings(project))


@router.put("/dev-settings")
def save_dev_settings(project: str, request: DevSettingsRequest, service: DevChecksService = Depends(dev_checks_service),
                      commands: CommandService = Depends(command_service)) -> DevSettingsResponse:
    if request.allowed_commands is not None:
        commands.save_allowed(project, request.allowed_commands)
    service.save_operator(project, request.operator_chatbot_id)
    if request.auto_retries is not None:
        service.save_auto_retries(project, request.auto_retries)
    return _response(project, service, commands, service.save_settings(project, request.test_scope, request.commands))


@router.get("/command-requests")
def command_requests(project: str, commands: CommandService = Depends(command_service)) -> list[CommandRequest]:
    """The commands the Operator asked for, waiting for an answer (the agent panel shows them)."""
    return commands.requests(project)


@router.post("/command-requests/answer", status_code=status.HTTP_204_NO_CONTENT)
def answer_command_request(project: str, answer: CommandAnswer, commands: CommandService = Depends(command_service)) -> Response:
    commands.answer(project, answer.command, allow=answer.allow, always=answer.always)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
