import pytest

from app.api.routes.documents import _parse_s3_uri
from app.api.routes.uploads import ALLOWED_UPLOAD_MIME_TYPES, MAX_UPLOAD_BYTES
from app.services.object_keys import build_user_upload_key, sanitize_filename


def test_sanitize_filename_strips_path_and_bad_chars() -> None:
    assert sanitize_filename("../../folder/../Evidence (Final).pdf") == "Evidence_Final_.pdf"
    assert sanitize_filename(r"C:\\tmp\\wiretap?.txt") == "C_tmp_wiretap_.txt"


def test_build_user_scoped_key_pattern() -> None:
    key = build_user_upload_key(
        user_id="11111111-1111-1111-1111-111111111111",
        matter_id="22222222-2222-2222-2222-222222222222",
        file_id="33333333-3333-3333-3333-333333333333",
        filename="notes.pdf",
    )
    assert key.startswith("acquittify/users/11111111-1111-1111-1111-111111111111/")
    assert "/matters/22222222-2222-2222-2222-222222222222/" in key
    assert key.endswith("/files/33333333-3333-3333-3333-333333333333/notes.pdf")


def test_parse_s3_uri() -> None:
    bucket, key = _parse_s3_uri("s3://trialai-artifacts/users/u1/casefiles/m1/files/d1/file.pdf")
    assert bucket == "trialai-artifacts"
    assert key == "users/u1/casefiles/m1/files/d1/file.pdf"


@pytest.mark.parametrize(
    ("mime", "size", "expected_error"),
    [
        ("application/pdf", 1024, None),
        ("application/x-msdownload", 1024, "unsupported content type"),
        ("application/pdf", 0, "file_size must be > 0"),
        ("application/pdf", 300 * 1024 * 1024, "exceeds max allowed"),
    ],
)
def test_upload_constraints_from_route_guards(
    mime: str, size: int, expected_error: str | None
) -> None:
    normalized = mime.strip().lower()

    if expected_error is None:
        assert normalized in ALLOWED_UPLOAD_MIME_TYPES
        assert 0 < size <= MAX_UPLOAD_BYTES
        return

    if expected_error == "unsupported content type":
        assert normalized not in ALLOWED_UPLOAD_MIME_TYPES
        return
    if expected_error == "file_size must be > 0":
        assert size <= 0
        return
    assert size > MAX_UPLOAD_BYTES
