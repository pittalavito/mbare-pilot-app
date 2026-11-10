"""«📌 Oggi» of a project, under /projects/{project}: the panel at the top of
the Attività tab, and its two quick actions on an item (check, new due date)."""
from datetime import date

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from controller.dependencies import today_service
from models.domain.today import Today
from service.today_service import TodayService

router = APIRouter(prefix="/projects/{project}", tags=["today"])


class ItemRequest(BaseModel):
    text: str
    """The item as the panel showed it: a changed item is refused (409)."""


class DueRequest(ItemRequest):
    due: date


@router.get("/today")
def today(project: str, service: TodayService = Depends(today_service)) -> Today:
    """What waits for the user, the items overdue and due soon, the activities to close."""
    return service.today(project)


@router.post("/activities/{note}/items/{item}/check", status_code=status.HTTP_204_NO_CONTENT)
def check_item(project: str, note: str, item: int, request: ItemRequest, service: TodayService = Depends(today_service)) -> Response:
    service.check_item(project, note, item, request.text)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/activities/{note}/items/{item}/due", status_code=status.HTTP_204_NO_CONTENT)
def set_due(project: str, note: str, item: int, request: DueRequest, service: TodayService = Depends(today_service)) -> Response:
    """«Rimanda»: the item's new due date."""
    service.set_due(project, note, item, request.text, request.due)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
