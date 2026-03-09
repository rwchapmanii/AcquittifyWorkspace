from app.workers.pipelines import process_document


def enqueue_document_pipeline(document_id: str) -> None:
    process_document(document_id)
