"""Folder picker endpoints — everything under /folders. Browsing is confined to
the configured PROJECT_ROOTS (paths outside them are a 400)."""
from fastapi import APIRouter, Depends

from controller.dependencies import project_service
from models.controller.project import FolderEntry, FolderListingResponse, FolderRootsResponse
from service.project_service import ProjectService

router = APIRouter(prefix="/folders", tags=["folders"])


@router.get("/roots")
def folder_roots(service: ProjectService = Depends(project_service)) -> FolderRootsResponse:
    return FolderRootsResponse(roots=[str(root) for root in service.folders.roots])


@router.get("")
def list_folder(path: str = "", show_hidden: bool = False,
                service: ProjectService = Depends(project_service)) -> FolderListingResponse:
    """The subfolders of ``path`` (empty = the first root)."""
    folders = service.folders
    folder = folders.resolve(path) if path.strip() else folders.roots[0]
    parent = folders.parent(folder)
    return FolderListingResponse(
        path=str(folder),
        parent=str(parent) if parent else None,
        subfolders=[FolderEntry(name=child.name, path=str(child)) for child in folders.subfolders(folder, show_hidden)],
    )
