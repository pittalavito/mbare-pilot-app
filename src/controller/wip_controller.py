"""«Elabora WIP» of a project, under /projects/{project}/wip: the note's state,
the preview of what the secretary's model would get (masked), the call that
returns the proposals, applying the chosen ones (no LLM) or dismissing them all."""
from fastapi import APIRouter, Depends

from controller.dependencies import wip_service
from models.controller.wip import WipApplyRequest, WipParagraphsRequest, WipRunRequest
from models.domain.wip import WipApplied, WipPreview, WipResult, WipRun, WipState
from service.wip_service import WipService

router = APIRouter(prefix="/projects/{project}/wip", tags=["wip"])


@router.get("")
def wip_state(project: str, service: WipService = Depends(wip_service)) -> WipState:
    """The note (``""`` when missing) and how many words of new text it has."""
    return service.state(project)


@router.get("/runs")
def wip_runs(project: str, service: WipService = Depends(wip_service)) -> list[WipRun]:
    """Every «Elabora WIP» of the project, newest first, with what the user did with its proposals."""
    return service.runs(project)


@router.post("/preview")
def wip_preview(project: str, request: WipParagraphsRequest, service: WipService = Depends(wip_service)) -> WipPreview:
    """The text the model would get, masked, with its aliases; ``mask{}`` terms are added to the map."""
    return service.preview(project, request.paragraphs)


@router.post("/process")
def wip_process(project: str, request: WipParagraphsRequest, service: WipService = Depends(wip_service)) -> WipResult:
    """One call to the secretary's model: the proposals, in clear (502 when the model fails)."""
    return service.process(project, request.paragraphs)


@router.post("/apply")
def wip_apply(project: str, request: WipApplyRequest, service: WipService = Depends(wip_service)) -> WipApplied:
    """The chosen proposals, then the sign in the note (409 when the WIP changed meanwhile)."""
    return service.apply(project, request.run_id, request.choices)


@router.post("/dismiss")
def wip_dismiss(project: str, request: WipRunRequest, service: WipService = Depends(wip_service)) -> WipRun:
    """The proposals closed without applying any: all discarded, no sign (409 when applied or dismissed already)."""
    return service.dismiss(project, request.run_id)
