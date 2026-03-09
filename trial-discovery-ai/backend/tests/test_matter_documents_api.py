import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.api.routes.documents as documents_route
from app.db.models.document import Document
from app.db.models.enums import DocumentStatus


def _csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("peregrine_csrf")
    assert token
    return {"X-CSRF-Token": token}


def _register(client: TestClient) -> dict:
    response = client.post(
        "/auth/register",
        json={
            "email": f"docs-{uuid.uuid4().hex}@example.test",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_matter(client: TestClient, *, name: str) -> str:
    response = client.post(
        "/matters",
        json={"name": name},
        headers=_csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_matter_documents_endpoint_returns_id_alias(
    client: TestClient, db_session: Session
) -> None:
    auth = _register(client)
    matter_id = _create_matter(client, name="Documents API Alias Matter")
    user_id = auth["user"]["id"]

    document = Document(
        matter_id=uuid.UUID(matter_id),
        uploaded_by_user_id=uuid.UUID(user_id),
        source_path="s3://acquittify-test/users/u/matters/m/documents/source.pdf",
        original_filename="source.pdf",
        mime_type="application/pdf",
        sha256="a" * 64,
        file_size=1024,
        page_count=1,
        status=DocumentStatus.PREPROCESSED,
    )
    db_session.add(document)
    db_session.commit()

    response = client.get(f"/matters/{matter_id}/documents?limit=100")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] >= 1
    assert body["documents"]

    first = body["documents"][0]
    expected_id = str(document.id)
    assert first["document_id"] == expected_id
    assert first["id"] == expected_id


def test_document_download_url_uses_presign_without_head_check(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    auth = _register(client)
    matter_id = _create_matter(client, name="Download URL Matter")
    user_id = auth["user"]["id"]

    document = Document(
        matter_id=uuid.UUID(matter_id),
        uploaded_by_user_id=uuid.UUID(user_id),
        source_path="s3://acquittify-test/users/u/matters/m/documents/source.pdf",
        original_filename="source.pdf",
        mime_type="application/pdf",
        sha256="b" * 64,
        file_size=2048,
        page_count=1,
        status=DocumentStatus.PREPROCESSED,
    )
    db_session.add(document)
    db_session.commit()

    class _FakeS3Client:
        def create_presigned_get_url(
            self, *, bucket: str, key: str, expires_in_seconds: int = 300
        ) -> str:
            assert bucket == "acquittify-test"
            assert key == "users/u/matters/m/documents/source.pdf"
            assert expires_in_seconds == 300
            return "https://example.test/presigned-download"

    monkeypatch.setattr(documents_route, "S3Client", _FakeS3Client)

    response = client.get(f"/documents/{document.id}/download-url")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["document_id"] == str(document.id)
    assert body["download_url"] == "https://example.test/presigned-download"
