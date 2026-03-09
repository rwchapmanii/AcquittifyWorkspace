from celery import chain

from app.db.session import get_session_factory
from app.services.chunk_and_embed import chunk_and_embed_document
from app.services.pass1 import run_pass1
from app.services.pass2 import run_pass2
from app.services.pass4 import run_pass4
from app.services.preprocess import preprocess_document
from app.workers.celery_app import celery_app


@celery_app.task
def preprocess_task(document_id: str) -> str:
    session_factory = get_session_factory()
    session = session_factory()
    try:
        preprocess_document(session=session, document_id=document_id)
        return document_id
    finally:
        session.close()


@celery_app.task
def chunk_and_embed_task(document_id: str) -> str:
    session_factory = get_session_factory()
    session = session_factory()
    try:
        chunk_and_embed_document(session=session, document_id=document_id)
        return document_id
    finally:
        session.close()


@celery_app.task
def pass1_task(document_id: str) -> str:
    session_factory = get_session_factory()
    session = session_factory()
    try:
        run_pass1(session=session, document_id=document_id)
        return document_id
    finally:
        session.close()


@celery_app.task
def pass2_task(document_id: str) -> str:
    session_factory = get_session_factory()
    session = session_factory()
    try:
        run_pass2(session=session, document_id=document_id)
        return document_id
    finally:
        session.close()


@celery_app.task
def pass4_task(document_id: str) -> str:
    session_factory = get_session_factory()
    session = session_factory()
    try:
        run_pass4(session=session, document_id=document_id)
        return document_id
    finally:
        session.close()


def build_document_chain(document_id: str):
    return chain(
        preprocess_task.s(document_id),
        chunk_and_embed_task.s(),
        pass1_task.s(),
        pass2_task.s(),
        pass4_task.s(),
    )
