from app.workers.tasks import build_document_chain


def process_document(document_id: str) -> None:
    build_document_chain(document_id).delay()


def process_document_inline(document_id: str) -> None:
    # Local fallback path when the broker is unavailable.
    build_document_chain(document_id).apply(throw=True)
