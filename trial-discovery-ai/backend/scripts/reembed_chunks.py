#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
if "" in sys.path:
    sys.path.remove("")

from sqlalchemy import delete, select  # noqa: E402

from app.db.session import get_session_factory  # noqa: E402
from app.db.models.artifact import Artifact  # noqa: E402
from app.db.models.chunk import Chunk  # noqa: E402
from app.db.models.document import Document  # noqa: E402
from app.db.models.enums import ArtifactKind  # noqa: E402
from app.services.chunk_and_embed import chunk_and_embed_document  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matter-id", dest="matter_id")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    session_factory = get_session_factory()
    session = session_factory()

    try:
        query = select(Document).order_by(Document.ingested_at.desc().nullslast())
        if args.matter_id:
            query = query.where(Document.matter_id == args.matter_id)
        if args.limit:
            query = query.limit(args.limit)

        documents = session.execute(query).scalars().all()
        if not documents:
            print("No documents found.")
            return 0

        print(f"Found {len(documents)} documents.")
        for idx, document in enumerate(documents, start=1):
            artifact = session.execute(
                select(Artifact).where(
                    Artifact.document_id == document.id,
                    Artifact.kind == ArtifactKind.EXTRACTED_TEXT,
                )
            ).scalar_one_or_none()
            if not artifact:
                print(f"[{idx}/{len(documents)}] skip {document.id} (no extracted text)")
                continue

            print(f"[{idx}/{len(documents)}] re-embed {document.id}")
            if args.dry_run:
                continue

            session.execute(delete(Chunk).where(Chunk.document_id == document.id))
            session.commit()
            chunk_and_embed_document(session=session, document_id=str(document.id))

        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
