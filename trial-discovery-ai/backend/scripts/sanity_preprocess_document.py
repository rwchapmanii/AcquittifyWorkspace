import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select

from app.db.models.artifact import Artifact
from app.db.models.enums import ArtifactKind
from app.db.session import get_session_factory
from app.services.preprocess import preprocess_document


def main() -> int:
    parser = argparse.ArgumentParser(description="Sanity-check preprocessing for one document.")
    parser.add_argument("document_id", help="Document UUID to preprocess")
    args = parser.parse_args()

    session_factory = get_session_factory()
    session = session_factory()
    try:
        result = preprocess_document(session=session, document_id=args.document_id)
        artifact = session.execute(
            select(Artifact).where(
                Artifact.document_id == args.document_id,
                Artifact.kind == ArtifactKind.EXTRACTED_TEXT,
            )
        ).scalar_one_or_none()
        print(f"Artifacts created: {result.artifacts_created}")
        print(f"OCR used: {result.ocr_used}")
        print(f"Extracted text artifact: {bool(artifact)}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
