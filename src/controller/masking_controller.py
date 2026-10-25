"""A project's masking map, under /projects/{project}/masking: the sensitive
values the LLM sees as aliases (registered by the tools or added by hand)."""
from fastapi import APIRouter, Depends, Response, status

from controller.dependencies import masking_service
from service.masking_service import MaskingService
from models.controller.masking import MaskEntryResponse, MaskRequest

router = APIRouter(prefix="/projects/{project}/masking", tags=["masking"])


@router.get("")
def list_masks(project: str, service: MaskingService = Depends(masking_service)) -> list[MaskEntryResponse]:
    return [MaskEntryResponse.from_entry(entry) for entry in service.entries(project)]


@router.post("", status_code=status.HTTP_201_CREATED)
def add_mask(project: str, request: MaskRequest, service: MaskingService = Depends(masking_service)) -> MaskEntryResponse:
    """A value to mask, added by hand; already in the map = the existing entry."""
    return MaskEntryResponse.from_entry(service.add_term(project, request.category, request.value))


@router.delete("/{alias}", status_code=status.HTTP_204_NO_CONTENT)
def remove_mask(project: str, alias: str, service: MaskingService = Depends(masking_service)) -> Response:
    """The value goes back to the LLM in clear; the alias is never reused."""
    service.remove(project, alias)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
