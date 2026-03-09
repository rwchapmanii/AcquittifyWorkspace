from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.matter import Matter
from app.db.models.organization import Organization
from app.storage.dropbox import DropboxClient


@dataclass(frozen=True)
class CaseFolder:
    name: str
    path: str


@dataclass(frozen=True)
class SyncResult:
    created: list[CaseFolder]
    existing: list[CaseFolder]


def list_case_folders(root_path: str | None = None) -> list[CaseFolder]:
    settings = get_settings()
    if root_path is None:
        case_root = settings.dropbox_case_root_path
    else:
        case_root = root_path
    if case_root is None:
        raise RuntimeError("DROPBOX_CASE_ROOT_PATH is not set")
    if case_root == "/":
        case_root = ""

    client = DropboxClient()
    if case_root.startswith("http://") or case_root.startswith("https://"):
        folders = client.list_folders_shared_link(case_root)
    else:
        folders = client.list_folders(case_root)
    cases: list[CaseFolder] = []
    for folder in folders:
        name = folder.name
        path = folder.path_display or folder.path_lower or name
        cases.append(CaseFolder(name=name, path=path))
    cases.sort(key=lambda item: item.name.lower())
    return cases


def sync_case_folders(
    *,
    session: Session,
    root_path: str | None = None,
    organization_id: UUID | None = None,
    created_by: str | None = None,
) -> SyncResult:
    if organization_id is None:
        organization_id = session.execute(
            select(Organization.id).order_by(Organization.created_at.asc())
        ).scalar_one_or_none()
        if organization_id is None:
            raise RuntimeError("No organizations found. Create a user first.")

    cases = list_case_folders(root_path=root_path)
    created: list[CaseFolder] = []
    existing: list[CaseFolder] = []

    for case in cases:
        matter = (
            session.query(Matter)
            .filter(
                Matter.external_id == case.path,
                Matter.organization_id == organization_id,
            )
            .first()
        )
        if matter:
            existing.append(case)
            continue

        matter = Matter(
            organization_id=organization_id,
            name=case.name,
            external_id=case.path,
            dropbox_root_path=case.path,
            created_by=created_by,
        )
        session.add(matter)
        created.append(case)

    session.commit()
    return SyncResult(created=created, existing=existing)
