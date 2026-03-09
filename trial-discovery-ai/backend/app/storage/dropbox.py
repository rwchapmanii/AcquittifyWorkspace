from dataclasses import dataclass
from typing import Iterable

import dropbox
from dropbox.files import FileMetadata, FolderMetadata

from app.core.config import get_settings


@dataclass(frozen=True)
class DropboxFile:
    path: str
    name: str
    size: int
    content_hash: str | None
    server_modified: str | None


class DropboxClient:
    def __init__(self, access_token: str | None = None) -> None:
        settings = get_settings()
        token = access_token or settings.dropbox_access_token
        refresh_token = settings.dropbox_refresh_token
        app_key = settings.dropbox_app_key
        app_secret = settings.dropbox_app_secret
        team_member_id = settings.dropbox_team_member_id

        if refresh_token and app_key and app_secret:
            if team_member_id:
                team_client = dropbox.DropboxTeam(
                    oauth2_refresh_token=refresh_token,
                    app_key=app_key,
                    app_secret=app_secret,
                )
                self._client = team_client.as_user(team_member_id)
            else:
                self._client = dropbox.Dropbox(
                    oauth2_refresh_token=refresh_token,
                    app_key=app_key,
                    app_secret=app_secret,
                )
        elif token:
            self._client = dropbox.Dropbox(oauth2_access_token=token)
        else:
            raise RuntimeError(
                "Dropbox credentials missing. Set DROPBOX_ACCESS_TOKEN or "
                "DROPBOX_REFRESH_TOKEN + DROPBOX_APP_KEY + DROPBOX_APP_SECRET."
            )

    def list_files(self, root_path: str, recursive: bool = True) -> Iterable[DropboxFile]:
        normalized = self._normalize_path(root_path)
        result = self._client.files_list_folder(normalized, recursive=recursive)
        yield from self._extract_files(result.entries)

        while result.has_more:
            result = self._client.files_list_folder_continue(result.cursor)
            yield from self._extract_files(result.entries)

    def list_entries_shared_link(
        self, shared_link_url: str, path: str = ""
    ) -> Iterable[FileMetadata | FolderMetadata]:
        link = dropbox.files.SharedLink(url=shared_link_url)
        normalized = self._normalize_path(path)
        result = self._client.files_list_folder(
            normalized, recursive=False, shared_link=link
        )
        yield from result.entries

        while result.has_more:
            result = self._client.files_list_folder_continue(result.cursor)
            yield from result.entries

    def list_files_shared_link(
        self, shared_link_url: str, path: str = ""
    ) -> Iterable[DropboxFile]:
        for entry in self.list_entries_shared_link(shared_link_url, path):
            if isinstance(entry, FileMetadata):
                yield from self._extract_files([entry])

    def list_files_shared_link_recursive(
        self, shared_link_url: str, path: str = ""
    ) -> Iterable[DropboxFile]:
        queue = [path]
        seen: set[str] = set()
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            for entry in self.list_entries_shared_link(shared_link_url, current):
                if isinstance(entry, FileMetadata):
                    if getattr(entry, "id", None):
                        rel_path = entry.id if str(entry.id).startswith("id:") else f"id:{entry.id}"
                    else:
                        base = current.strip("/")
                        if base:
                            rel_path = f"/{base}/{entry.name}"
                        else:
                            rel_path = f"/{entry.name}"
                    yield DropboxFile(
                        path=rel_path,
                        name=entry.name,
                        size=entry.size,
                        content_hash=getattr(entry, "content_hash", None),
                        server_modified=entry.server_modified.isoformat()
                        if entry.server_modified
                        else None,
                    )
                elif isinstance(entry, FolderMetadata):
                    base = current.strip("/")
                    if base:
                        next_path = f"{base}/{entry.name}"
                    else:
                        next_path = entry.name or ""
                    queue.append(next_path)

    def list_folders(self, root_path: str) -> list[FolderMetadata]:
        result = self._client.files_list_folder(root_path, recursive=False)
        folders = [entry for entry in result.entries if isinstance(entry, FolderMetadata)]
        while result.has_more:
            result = self._client.files_list_folder_continue(result.cursor)
            folders.extend(
                [entry for entry in result.entries if isinstance(entry, FolderMetadata)]
            )
        return folders

    def list_folders_shared_link(self, shared_link_url: str) -> list[FolderMetadata]:
        link = dropbox.files.SharedLink(url=shared_link_url)
        result = self._client.files_list_folder("", recursive=False, shared_link=link)
        folders = [entry for entry in result.entries if isinstance(entry, FolderMetadata)]
        while result.has_more:
            result = self._client.files_list_folder_continue(result.cursor)
            folders.extend(
                [entry for entry in result.entries if isinstance(entry, FolderMetadata)]
            )
        return folders

    @staticmethod
    def _extract_files(entries) -> Iterable[DropboxFile]:
        for entry in entries:
            if isinstance(entry, FileMetadata):
                path = entry.path_lower or entry.path_display or entry.name
                if path and not path.startswith(("/", "id:", "ns:")):
                    path = f"/{path}"
                yield DropboxFile(
                    path=path,
                    name=entry.name,
                    size=entry.size,
                    content_hash=getattr(entry, "content_hash", None),
                    server_modified=entry.server_modified.isoformat()
                    if entry.server_modified
                    else None,
                )

    def download(self, path: str) -> bytes:
        settings = get_settings()
        shared_link_root = settings.dropbox_case_root_path or ""
        normalized = self._normalize_path(path)
        if normalized.startswith(("id:", "ns:")):
            metadata, response = self._client.files_download(normalized)
        elif shared_link_root.startswith("http://") or shared_link_root.startswith("https://"):
            metadata, response = self._client.sharing_get_shared_link_file(
                url=shared_link_root,
                path=normalized,
            )
        else:
            metadata, response = self._client.files_download(normalized)
        _ = metadata
        return response.content

    @staticmethod
    def _normalize_path(path: str) -> str:
        if not path:
            return ""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if path.startswith("/") or path.startswith("id:") or path.startswith("ns:"):
            return path
        return f"/{path}"
