import logging
import threading
from collections.abc import Callable

from app.workers.pipelines import process_document, process_document_inline
from app.workers.tasks import pass1_task

logger = logging.getLogger(__name__)


def _run_detached(
    *,
    document_id: str,
    task_name: str,
    target: Callable[[], None],
) -> None:
    def _runner() -> None:
        try:
            target()
        except Exception:  # noqa: BLE001
            logger.exception("%s failed for document_id=%s", task_name, document_id)

    thread = threading.Thread(
        target=_runner,
        daemon=True,
        name=f"{task_name}-{document_id[:8]}",
    )
    thread.start()


def enqueue_document_pipeline(document_id: str) -> None:
    try:
        process_document(document_id)
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to enqueue full document pipeline for document_id=%s; "
            "falling back to local execution.",
            document_id,
        )
        _run_detached(
            document_id=document_id,
            task_name="document-pipeline-inline",
            target=lambda: process_document_inline(document_id),
        )


def enqueue_bootstrap_pass(document_id: str) -> None:
    try:
        pass1_task.delay(document_id)
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to enqueue bootstrap pass for document_id=%s; "
            "falling back to local pass1 execution.",
            document_id,
        )
        _run_detached(
            document_id=document_id,
            task_name="bootstrap-pass1-inline",
            target=lambda: pass1_task.apply(args=(document_id,), throw=True),
        )
