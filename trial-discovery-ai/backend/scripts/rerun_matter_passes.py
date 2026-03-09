import argparse
import sys
from pathlib import Path
from typing import Callable

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.document import Document
from app.db.models.matter import Matter
from app.db.session import get_session_factory
from app.services.pass1 import run_pass1
from app.services.pass2 import run_pass2
from app.services.pass4 import run_pass4


PASS_FUNCS: dict[int, Callable[[Session, str], object]] = {
    1: run_pass1,
    2: run_pass2,
    4: run_pass4,
}


def _parse_passes(value: str) -> list[int]:
    passes: list[int] = []
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            pass_num = int(raw)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"Invalid pass number: {raw}") from exc
        if pass_num not in PASS_FUNCS:
            raise argparse.ArgumentTypeError("Passes must be 1, 2, or 4")
        passes.append(pass_num)
    if not passes:
        raise argparse.ArgumentTypeError("Provide at least one pass number")
    return passes


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-run pass1/pass2/pass4 for all documents in a matter."
    )
    parser.add_argument("--matter-id", help="Exact matter id (UUID)")
    parser.add_argument("--matter-name", help="Matter name substring (case-insensitive)")
    parser.add_argument(
        "--passes",
        default="1,2,4",
        type=_parse_passes,
        help="Comma-separated list of passes to run (default: 1,2,4)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit documents")
    parser.add_argument("--dry-run", action="store_true", help="List documents only")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue if a document fails",
    )
    args = parser.parse_args()

    session_factory = get_session_factory()
    session = session_factory()
    try:
        matter = _resolve_matter(session, args.matter_id, args.matter_name)
        total = session.execute(
            select(func.count()).select_from(Document).where(Document.matter_id == matter.id)
        ).scalar_one()
        if args.limit:
            total = min(total, args.limit)
        print(f"Matter: {matter.name} ({matter.id})")
        print(f"Documents: {total}")
        print(f"Passes: {', '.join(str(p) for p in args.passes)}")

        query = (
            select(Document)
            .where(Document.matter_id == matter.id)
            .order_by(Document.ingested_at.asc().nullslast())
        )
        if args.limit:
            query = query.limit(args.limit)

        rows = session.execute(query).scalars().all()
        for idx, doc in enumerate(rows, start=1):
            status = getattr(doc.status, "value", doc.status)
            print(f"[{idx}/{total}] {doc.id} {doc.original_filename} ({status})")
            if args.dry_run:
                continue
            for pass_num in args.passes:
                try:
                    PASS_FUNCS[pass_num](session=session, document_id=str(doc.id))
                except Exception as exc:  # noqa: BLE001
                    session.rollback()
                    print(f"  Pass {pass_num} failed: {exc}")
                    if not args.continue_on_error:
                        raise
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
