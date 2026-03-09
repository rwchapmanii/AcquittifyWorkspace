from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.db.models.document import Document
from app.db.models.enums import DocumentStatus
from app.services.object_keys import build_user_upload_key
from app.services.pipelines import enqueue_document_pipeline
from app.services.usage_metrics import record_document_upload
from app.storage.s3 import S3Client


@dataclass(frozen=True)
class UploadResult:
    document_id: str


def upload_local_file(
    *,
    session: Session,
    matter_id: str,
    user_id: str,
    organization_id: str,
    filename: str,
    content_type: str | None,
    data: bytes,
) -> UploadResult:
    file_hash = sha256(data).hexdigest()
    file_size = len(data)
    document_id = uuid4()
    matter_uuid = UUID(matter_id)
    user_uuid = UUID(user_id)
    organization_uuid = UUID(organization_id)

    s3 = S3Client()
    key = build_user_upload_key(
        user_id=user_id,
        matter_id=matter_id,
        file_id=str(document_id),
        filename=filename,
    )
    obj_ref = s3.put_bytes(
        key=key,
        data=data,
        content_type=content_type or "application/octet-stream",
    )

    document = Document(
        id=document_id,
        matter_id=matter_uuid,
        uploaded_by_user_id=user_uuid,
        source_path=obj_ref.uri,
        original_filename=filename,
        mime_type=content_type or "application/octet-stream",
        sha256=file_hash,
        file_size=file_size,
        page_count=None,
        ingested_at=datetime.now(timezone.utc),
        status=DocumentStatus.NEW,
    )
    session.add(document)
    session.flush()
    record_document_upload(
        session=session,
        user_id=user_uuid,
        organization_id=organization_uuid,
        matter_id=matter_uuid,
        document_id=document_id,
        file_size=file_size,
        original_filename=filename,
    )

    enqueue_document_pipeline(str(document.id))
    session.commit()
    return UploadResult(document_id=str(document.id))
