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
from app.services.pass1 import run_pass1


def _has_extracted_text(session, document_id: str) -> bool:
    artifact = session.execute(
        select(Artifact).where(
            Artifact.document_id == document_id,
            Artifact.kind == ArtifactKind.EXTRACTED_TEXT,
        )
    ).scalar_one_or_none()
    return artifact is not None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sanity-check pass1 auto-preprocess behavior."
    )
    parser.add_argument("document_id", help="Document UUID to test")
    args = parser.parse_args()

    session_factory = get_session_factory()
    session = session_factory()
    try:
        before = _has_extracted_text(session, args.document_id)
        print(f"Extracted text before: {before}")
        run_pass1(session=session, document_id=args.document_id)
        after = _has_extracted_text(session, args.document_id)
        print(f"Extracted text after: {after}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
