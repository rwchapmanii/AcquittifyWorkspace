import re
from pathlib import PurePosixPath

_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_FILENAME_LENGTH = 180


def sanitize_filename(filename: str) -> str:
    raw_name = PurePosixPath(filename or "").name.strip()
    if not raw_name:
        return "upload.bin"

    safe_name = _UNSAFE_FILENAME.sub("_", raw_name).strip("._")
    if not safe_name:
        return "upload.bin"
    return safe_name[:_MAX_FILENAME_LENGTH]


def build_user_upload_key(
    *,
    user_id: str,
    matter_id: str,
    file_id: str,
    filename: str,
) -> str:
    safe_name = sanitize_filename(filename)
    return f"acquittify/users/{user_id}/matters/{matter_id}/files/{file_id}/{safe_name}"
