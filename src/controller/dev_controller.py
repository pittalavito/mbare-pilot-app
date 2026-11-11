"""The checks around a development delegated to Copilot (blocco 09), under
/projects/{project}: the tests' settings and whether the project has the two
automations («Prepara sviluppo», «Verifica sviluppo»)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from controller.dependencies import dev_checks_service
from models.domain.dev import PREPARE_AUTOMATION, VERIFY_AUTOMATION, DevSettings, TestScope
from service.dev_checks_service import DevChecksService

router = APIRouter(prefix="/projects/{project}", tags=["dev"])


class DevSettingsResponse(DevSettings):
    prepare_automation: bool
    """The project has «Prepara sviluppo» (switched on): the delegation offers to prepare the repositories."""
    verify_automation: bool
    """The project has «Verifica sviluppo» (switched on): it runs when a development goes «to verify»."""


class DevSettingsRequest(BaseModel):
    test_scope: TestScope = TestScope.ALL
    commands: dict[str, str] = {}
    """Repository folder → the tests' command; empty or missing = the detected one."""


def _response(project: str, service: DevChecksService, settings: DevSettings) -> DevSettingsResponse:
    return DevSettingsResponse(**settings.model_dump(), prepare_automation=service.has(project, PREPARE_AUTOMATION),
                               verify_automation=service.has(project, VERIFY_AUTOMATION))


@router.get("/dev-settings")
def dev_settings(project: str, service: DevChecksService = Depends(dev_checks_service)) -> DevSettingsResponse:
    """Each repository's tests (tool, detected command, the one written), the default scope, the two automations."""
    return _response(project, service, service.settings(project))


@router.put("/dev-settings")
def save_dev_settings(project: str, request: DevSettingsRequest,
                      service: DevChecksService = Depends(dev_checks_service)) -> DevSettingsResponse:
    return _response(project, service, service.save_settings(project, request.test_scope, request.commands))
