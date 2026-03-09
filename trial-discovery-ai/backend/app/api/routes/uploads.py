from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import AuthContext
from app.api.authz import require_write_access, resolve_matter_for_org
from app.api.deps import get_db
from app.db.models.matter import Matter
from app.services.object_keys import build_user_upload_key
from app.services.uploads import upload_local_file
from app.storage.s3 import S3Client

router = APIRouter(prefix="/matters", tags=["uploads"])

ALLOWED_UPLOAD_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/csv",
    "application/json",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/jpeg",
    "image/png",
}
MAX_UPLOAD_BYTES = 250 * 1024 * 1024


class PresignUploadRequest(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"
    expires_in_seconds: int = Field(default=300, ge=60, le=900)


def _resolve_matter(
    *, session: Session, matter_id: str, auth: AuthContext
) -> Matter | None:
    return resolve_matter_for_org(
        session=session, matter_id=matter_id, organization_id=auth.organization.id
    )


@router.post("/{matter_id}/ingest/upload")
async def upload_document(
    matter_id: str,
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_write_access),
) -> dict:
    matter = _resolve_matter(session=session, matter_id=matter_id, auth=auth)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    document_ids = []
    for file in files:
        data = await file.read()
        content_type = (file.content_type or "application/octet-stream").strip().lower()
        if content_type not in ALLOWED_UPLOAD_MIME_TYPES:
            raise HTTPException(status_code=415, detail="Unsupported file type")
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds maximum upload size")
        result = upload_local_file(
            session=session,
            matter_id=str(matter.id),
            user_id=str(auth.user.id),
            organization_id=str(auth.organization.id),
            filename=file.filename or "upload.bin",
            content_type=content_type,
            data=data,
        )
        document_ids.append(result.document_id)
    return {"document_ids": document_ids}


@router.post("/{matter_id}/ingest/presign-upload")
def create_presigned_upload_url(
    matter_id: str,
    payload: PresignUploadRequest,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_write_access),
) -> dict:
    matter = _resolve_matter(session=session, matter_id=matter_id, auth=auth)
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    content_type = (payload.content_type or "application/octet-stream").strip().lower()
    if content_type not in ALLOWED_UPLOAD_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported file type")

    file_id = str(uuid4())
    object_key = build_user_upload_key(
        user_id=str(auth.user.id),
        matter_id=str(matter.id),
        file_id=file_id,
        filename=payload.filename,
    )
    s3 = S3Client()
    upload_url = s3.create_presigned_put_url(
        key=object_key,
        content_type=content_type,
        expires_in_seconds=payload.expires_in_seconds,
    )
    return {
        "file_id": file_id,
        "key": object_key,
        "content_type": content_type,
        "expires_in_seconds": payload.expires_in_seconds,
        "upload_url": upload_url,
    }
