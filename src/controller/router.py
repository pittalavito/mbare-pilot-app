"""API composition: one router per scope, each declaring its own prefix.
core/app.py includes only the aggregate ``router`` below — adding a scope
means adding a ``<scope>_controller.py`` and one include here."""
from fastapi import APIRouter

from controller.admin_controller import router as admin_router
from controller.agent_controller import router as agent_router
from controller.atlassian_controller import router as atlassian_router
from controller.catalog_controller import router as catalog_router
from controller.chatbot_controller import router as chatbot_router
from controller.context_controller import router as context_router
from controller.copilot_controller import router as copilot_router
from controller.definition_controller import router as definition_router
from controller.dev_controller import router as dev_router
from controller.folder_controller import router as folder_router
from controller.git_controller import router as git_router
from controller.masking_controller import router as masking_router
from controller.metrics_controller import router as metrics_router
from controller.pipeline_controller import router as pipeline_router
from controller.plan_controller import router as plan_router
from controller.process_controller import router as process_router
from controller.project_controller import router as project_router
from controller.project_data_controller import router as project_data_router
from controller.publish_controller import router as publish_router
from controller.role_controller import router as role_router
from controller.today_controller import router as today_router
from controller.wip_controller import router as wip_router

router = APIRouter()


@router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness probe for the UI and the run scripts."""
    return {"status": "ok"}


router.include_router(project_router)
router.include_router(folder_router)
router.include_router(agent_router)
router.include_router(role_router)
router.include_router(catalog_router)
router.include_router(chatbot_router)
router.include_router(project_data_router)
router.include_router(git_router)
router.include_router(pipeline_router)
router.include_router(atlassian_router)
router.include_router(admin_router)
router.include_router(masking_router)
router.include_router(definition_router)
router.include_router(process_router)
router.include_router(copilot_router)
router.include_router(wip_router)
router.include_router(plan_router)
router.include_router(context_router)
router.include_router(metrics_router)
router.include_router(today_router)
router.include_router(dev_router)
router.include_router(publish_router)
