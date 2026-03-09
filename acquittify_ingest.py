"""Deprecated entrypoint. Use scripts/unified_ingest.py instead."""

from acquittify.ingest.unified import ingest_local_corpus
from acquittify.paths import CHROMA_DIR, RAW_CORPUS_DIR


def main() -> None:
    print("acquittify_ingest.py is deprecated; using unified ingestion pipeline.")
    ingest_local_corpus(RAW_CORPUS_DIR, CHROMA_DIR)


if __name__ == "__main__":
    main()
