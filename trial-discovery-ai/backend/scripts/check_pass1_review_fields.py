import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.document import Document
from app.db.models.matter import Matter
from app.db.models.pass_run import PassRun
from app.db.session import get_session_factory

REVIEW_FIELDS = ("document_type", "witnesses", "document_date", "relevance", "proponent")


def _resolve_matter(session: Session, matter_id: str | None, matter_name: str | None) -> Matter:
    if matter_id:
        matter = session.get(Matter, matter_id)
        if not matter:
            raise SystemExit(f"No matter found with id {matter_id}")
        return matter
    if not matter_name:
        raise SystemExit("Provide --matter-id or --matter-name")

    matches = (
        session.execute(
            select(Matter).where(Matter.name.ilike(f"%{matter_name}%"))
        )
        .scalars()
        .all()
    )
    if not matches:
        raise SystemExit(f"No matters found matching name '{matter_name}'")
    if len(matches) > 1:
        print("Multiple matters matched. Provide --matter-id instead:")
        for matter in matches:
            print(f"- {matter.id} {matter.name}")
        raise SystemExit(1)
    return matches[0]


def _latest_pass1(session: Session, document_id: str) -> dict | None:
    row = (
        session.execute(
            select(PassRun.output_json)
            .where(
                PassRun.document_id == document_id,
                PassRun.pass_num == 1,
                PassRun.is_latest.is_(True),
            )
            .limit(1)
        )
        .scalars()
        .first()
    )
    return row


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect latest pass1 output for review fields."
    )
    parser.add_argument("--matter-id", help="Exact matter id (UUID)")
    parser.add_argument("--matter-name", help="Matter name substring (case-insensitive)")
    parser.add_argument("--limit", type=int, default=10, help="Limit documents")
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Show only documents missing any review fields",
    )
    args = parser.parse_args()

    session_factory = get_session_factory()
    session = session_factory()
    try:
        matter = _resolve_matter(session, args.matter_id, args.matter_name)
        docs = (
            session.execute(
                select(Document)
                .where(Document.matter_id == matter.id)
                .order_by(Document.ingested_at.desc().nullslast())
                .limit(args.limit)
            )
            .scalars()
            .all()
        )
        print(f"Matter: {matter.name} ({matter.id})")
        for doc in docs:
            output = _latest_pass1(session, str(doc.id)) or {}
            values = {key: output.get(key) for key in REVIEW_FIELDS}
            missing = [key for key, value in values.items() if value in (None, [], "")]
            if args.missing_only and not missing:
                continue
            print(f"- {doc.original_filename} ({doc.id})")
            for key in REVIEW_FIELDS:
                print(f"  {key}: {values.get(key)}")
            if missing:
                print(f"  missing: {', '.join(missing)}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
