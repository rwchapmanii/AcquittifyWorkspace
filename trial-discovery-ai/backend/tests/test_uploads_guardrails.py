import os

import pytest

from app.core.config import get_settings
from app.services.uploads import (
    _validate_upload_constraints,
    build_user_scoped_key,
    parse_s3_uri,
    sanitize_filename,
)


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_sanitize_filename_strips_path_and_bad_chars() -> None:
    assert sanitize_filename("../../folder/../Evidence (Final).pdf") == "Evidence__Final_.pdf"
    assert sanitize_filename(r"C:\\tmp\\wiretap?.txt") == "wiretap_.txt"


def test_build_user_scoped_key_pattern() -> None:
    key = build_user_scoped_key(
        user_id="11111111-1111-1111-1111-111111111111",
        matter_id="22222222-2222-2222-2222-222222222222",
        document_id="33333333-3333-3333-3333-333333333333",
        original_filename="notes.pdf",
    )
    assert key.startswith("users/11111111-1111-1111-1111-111111111111/")
    assert "/casefiles/22222222-2222-2222-2222-222222222222/" in key
    assert key.endswith("/files/33333333-3333-3333-3333-333333333333/notes.pdf")


def test_parse_s3_uri() -> None:
    bucket, key = parse_s3_uri("s3://trialai-artifacts/users/u1/casefiles/m1/files/d1/file.pdf")
    assert bucket == "trialai-artifacts"
    assert key == "users/u1/casefiles/m1/files/d1/file.pdf"


@pytest.mark.parametrize(
    ("mime", "size", "expected_error"),
    [
        ("application/pdf", 1024, None),
        ("application/x-msdownload", 1024, "unsupported content type"),
        ("application/pdf", 0, "file_size must be > 0"),
        ("application/pdf", 60 * 1024 * 1024, "exceeds max allowed"),
    ],
)
def test_validate_upload_constraints(mime: str, size: int, expected_error: str | None) -> None:
    os.environ["UPLOAD_ALLOWED_MIME_TYPES"] = "application/pdf,image/*"
    os.environ["UPLOAD_MAX_DOCUMENT_BYTES"] = str(50 * 1024 * 1024)
    os.environ["UPLOAD_MULTIPART_THRESHOLD_BYTES"] = str(120 * 1024 * 1024)
    get_settings.cache_clear()

    if expected_error is None:
        _validate_upload_constraints(content_type=mime, file_size=size)
        return

    with pytest.raises(ValueError, match=expected_error):
        _validate_upload_constraints(content_type=mime, file_size=size)
