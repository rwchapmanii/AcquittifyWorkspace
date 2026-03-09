import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acquittify.ingest.unified import ingest_local_corpus, ingest_courtlistener, ingest_courtlistener_db, ingest_pdf_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Unified ingestion for local corpus + CourtListener into Chroma.")
    parser.add_argument("--chroma-dir", default="Corpus/Chroma", help="Chroma directory")
    parser.add_argument("--raw-dir", default="Corpus/Raw", help="Local corpus directory")
    parser.add_argument("--local", action="store_true", help="Ingest local corpus PDFs (Corpus/Raw)")
    parser.add_argument("--pdf", action="append", help="Specific PDF path to ingest (can be used multiple times)")
    parser.add_argument("--courtlistener", action="store_true", help="Ingest CourtListener API records")
    parser.add_argument("--courtlistener-db", action="store_true", help="Ingest CourtListener records from Postgres raw schema")
    parser.add_argument("--db-dsn", default=None, help="Postgres DSN for CourtListener raw schema")
    parser.add_argument("--db-limit", type=int, default=None, help="Limit number of opinions ingested from DB")
    parser.add_argument("--db-since", default=None, help="Date filter for DB ingest (YYYY-MM-DD)")
    parser.add_argument("--since", default=None, help="CourtListener since date (YYYY-MM-DD)")
    parser.add_argument("--max-pages", type=int, default=1, help="CourtListener max pages per endpoint")
    parser.add_argument("--no-taxonomy", action="store_true", help="Skip taxonomy classification")
    parser.add_argument("--skip-summary", action="store_true", help="Skip LLM summary metadata for local corpus")
    args = parser.parse_args()

    chroma_dir = Path(args.chroma_dir)
    raw_dir = Path(args.raw_dir)
    use_taxonomy = not args.no_taxonomy

    if not args.local and not args.courtlistener and not args.courtlistener_db:
        args.local = True

    if args.local:
        ingest_local_corpus(raw_dir, chroma_dir, use_taxonomy=use_taxonomy, skip_summary=args.skip_summary)

    if args.pdf:
        pdf_paths = [Path(p) for p in args.pdf]
        ingest_pdf_paths(pdf_paths, chroma_dir, use_taxonomy=use_taxonomy, skip_summary=args.skip_summary)

    if args.courtlistener:
        ingest_courtlistener(chroma_dir, since=args.since, max_pages=args.max_pages, use_taxonomy=use_taxonomy)

    if args.courtlistener_db:
        dsn = args.db_dsn or "postgresql://acquittify:acquittify@localhost:5432/courtlistener"
        ingest_courtlistener_db(
            chroma_dir,
            dsn=dsn,
            since=args.db_since,
            limit=args.db_limit,
            use_taxonomy=use_taxonomy,
        )


if __name__ == "__main__":
    main()
