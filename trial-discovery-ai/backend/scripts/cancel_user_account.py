#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select

from app.db.models.artifact import Artifact
from app.db.models.chunk import Chunk
from app.db.models.document import Document
from app.db.models.document_entity import DocumentEntity
from app.db.models.exhibit import Exhibit
from app.db.models.pass_run import PassRun
from app.db.models.user import User
from app.db.models.user_action import UserAction
from app.db.session import get_session_factory
from app.storage.s3 import S3Client


def _parse_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid UUID: {value}") from exc


def _write_audit(audit_path: Path, payload: dict) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Lock a user account and hard-delete that user's uploaded documents "
            "from DB + S3 user prefix."
        )
    )
    parser.add_argument("--user-id", required=True, type=_parse_uuid)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform changes. Without this flag, command runs as dry-run.",
    )
    parser.add_argument(
        "--audit-path",
        default="reports/account_cancellation_audit.jsonl",
        help="Audit JSONL output path.",
    )
    args = parser.parse_args()

    user_id: UUID = args.user_id
    audit_path = Path(args.audit_path)

    session_factory = get_session_factory()
    with session_factory() as session:
        user = session.get(User, user_id)
        if not user:
            print(json.dumps({"status": "error", "detail": "user_not_found", "user_id": str(user_id)}))
            return 1

        docs = session.execute(
            select(Document.id).where(Document.uploaded_by == user_id)
        ).scalars().all()
        doc_count = len(docs)
        s3_prefix = f"users/{user_id}/"

        payload = {
            "event": "account_cancellation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": str(user_id),
            "dry_run": not args.apply,
            "documents_targeted": doc_count,
            "s3_prefix": s3_prefix,
        }

        if not args.apply:
            print(json.dumps(payload, ensure_ascii=True))
            return 0

        s3 = S3Client()
        deleted_objects = s3.delete_prefix(prefix=s3_prefix)

        if docs:
            session.execute(delete(UserAction).where(UserAction.document_id.in_(docs)))
            session.execute(delete(Exhibit).where(Exhibit.document_id.in_(docs)))
            session.execute(delete(DocumentEntity).where(DocumentEntity.document_id.in_(docs)))
            session.execute(delete(Chunk).where(Chunk.document_id.in_(docs)))
            session.execute(delete(Artifact).where(Artifact.document_id.in_(docs)))
            session.execute(delete(PassRun).where(PassRun.document_id.in_(docs)))
            session.execute(delete(Document).where(Document.id.in_(docs)))

        user.is_active = False
        session.commit()

        payload["deleted_objects"] = deleted_objects
        payload["documents_deleted"] = doc_count
        payload["account_locked"] = True
        payload["completed_at"] = datetime.now(timezone.utc).isoformat()
        _write_audit(audit_path, payload)
        print(json.dumps(payload, ensure_ascii=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
