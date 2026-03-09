#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
if "" in sys.path:
    sys.path.remove("")

from sqlalchemy import select  # noqa: E402

from app.db.session import get_session_factory  # noqa: E402
from app.db.models.artifact import Artifact  # noqa: E402
from app.db.models.document import Document  # noqa: E402
from app.db.models.enums import ArtifactKind  # noqa: E402
from app.services.embedding import embed_text  # noqa: E402
from app.services.embedding_context import (  # noqa: E402
    augment_for_embedding,
    build_embedding_context,
)
from app.storage.s3 import S3Client  # noqa: E402


def _load_extracted(session, document_id: str) -> dict:
    artifact = session.execute(
        select(Artifact).where(
            Artifact.document_id == document_id,
            Artifact.kind == ArtifactKind.EXTRACTED_TEXT,
        )
    ).scalar_one_or_none()
    if not artifact:
        raise RuntimeError("Extracted text artifact not found")
    s3 = S3Client()
    return _load_json(s3, artifact.uri)


def _load_json(s3: S3Client, uri: str) -> dict:
    if not uri.startswith("s3://"):
        raise ValueError("Invalid S3 URI")
    parts = uri.replace("s3://", "", 1).split("/", 1)
    bucket = parts[0]
    key = parts[1]
    data = s3.get_bytes(bucket=bucket, key=key).decode("utf-8")
    return __import__("json").loads(data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("document_id", help="Document UUID to inspect")
    parser.add_argument("--run-embedding", action="store_true")
    args = parser.parse_args()

    session_factory = get_session_factory()
    session = session_factory()
    try:
        document = session.get(Document, args.document_id)
        if not document:
            raise RuntimeError("Document not found")
        extracted = _load_extracted(session, str(document.id))
        context = build_embedding_context(document, extracted)
        print("Embedding header preview:")
        print(context.header)
        print("\nSummary preview:")
        print(context.summary[:500])

        if args.run_embedding:
            sample_text = extracted.get("pages", [{}])[0].get("text", "")
            embedding_input = augment_for_embedding(context.header, sample_text)
            vector = embed_text(embedding_input).vector
            print(f"Embedding vector dims: {len(vector)}")
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
