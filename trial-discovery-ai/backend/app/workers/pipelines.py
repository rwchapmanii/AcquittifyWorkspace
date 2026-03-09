from app.workers.tasks import build_document_chain


def process_document(document_id: str) -> None:
    build_document_chain(document_id).delay()
