#!/usr/bin/env python3
"""
Dropbox Service - List and download files from Dropbox.

Provides Dropbox API operations for scanning workflow.
Uses App Folder access - all paths are relative to /Apps/<app_name>/.
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

import dropbox
from dropbox.exceptions import ApiError
from dropbox.files import FileMetadata, FolderMetadata

from cloud_services.dropbox_auth import DropboxAuth

logger = logging.getLogger(__name__)

# Supported file extensions for scanning
SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"
}


class DropboxService:
    """
    Dropbox API service wrapper.

    Provides methods for listing, downloading, and moving files
    in Dropbox folders. Uses App Folder access, so all paths are
    relative to /Apps/<app_name>/.
    """

    def __init__(self, auth: Optional[DropboxAuth] = None):
        """
        Initialize Dropbox service.

        Args:
            auth: DropboxAuth instance (creates one if not provided)
        """
        self._auth = auth or DropboxAuth()
        self._client = None

    @property
    def client(self) -> dropbox.Dropbox:
        """Get the Dropbox client (lazy load)."""
        if self._client is None:
            self._client = self._auth.client
        return self._client

    def _normalize_path(self, path: str) -> str:
        """
        Normalize path for Dropbox API.

        Dropbox paths must start with / (except empty string for root).
        """
        if not path:
            return ""
        if not path.startswith("/"):
            path = "/" + path
        return path

    def list_files(
        self,
        folder_path: str = "",
        extensions: Optional[set] = None,
    ) -> List[Dict[str, Any]]:
        """
        List files in a Dropbox folder.

        Args:
            folder_path: Path relative to app folder (empty = root)
            extensions: Filter to specific extensions (default: images + PDFs)

        Returns:
            List of file metadata dicts (compatible with DriveService format)
        """
        if extensions is None:
            extensions = SUPPORTED_EXTENSIONS

        path = self._normalize_path(folder_path)
        files = []

        try:
            # List folder contents
            result = self.client.files_list_folder(path)

            while True:
                for entry in result.entries:
                    # Only include files (not folders)
                    if isinstance(entry, FileMetadata):
                        # Check extension
                        ext = entry.name.lower().split(".")[-1] if "." in entry.name else ""
                        if f".{ext}" in extensions or not extensions:
                            files.append(self._metadata_to_dict(entry))

                # Handle pagination
                if result.has_more:
                    result = self.client.files_list_folder_continue(result.cursor)
                else:
                    break

        except ApiError as e:
            if e.error.is_path() and e.error.get_path().is_not_found():
                logger.warning(f"Folder not found: {path}")
            else:
                raise

        return files

    def _metadata_to_dict(self, metadata: FileMetadata) -> Dict[str, Any]:
        """
        Convert Dropbox FileMetadata to dict format compatible with DriveService.

        Args:
            metadata: Dropbox FileMetadata object

        Returns:
            Dict with standardized keys
        """
        # Determine MIME type from extension
        ext = metadata.name.lower().split(".")[-1] if "." in metadata.name else ""
        mime_type = self._ext_to_mime(ext)

        return {
            "id": metadata.path_display,  # Use path as ID for Dropbox
            "name": metadata.name,
            "mimeType": mime_type,
            "size": metadata.size,
            "createdTime": metadata.server_modified.isoformat(),
            "path_display": metadata.path_display,
            "path_lower": metadata.path_lower,
        }

    def _ext_to_mime(self, ext: str) -> str:
        """Convert file extension to MIME type."""
        mime_map = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
            "gif": "image/gif",
            "pdf": "application/pdf",
        }
        return mime_map.get(ext, "application/octet-stream")

    def download_file(self, file_path: str) -> bytes:
        """
        Download file content from Dropbox.

        Args:
            file_path: Full path to file (or path_display from list_files)

        Returns:
            File content as bytes
        """
        path = self._normalize_path(file_path)

        try:
            metadata, response = self.client.files_download(path)
            return response.content
        except ApiError as e:
            logger.error(f"Failed to download {path}: {e}")
            raise

    def get_file_metadata(self, file_path: str) -> Dict[str, Any]:
        """
        Get file metadata.

        Args:
            file_path: Path to file

        Returns:
            File metadata dict
        """
        path = self._normalize_path(file_path)

        try:
            metadata = self.client.files_get_metadata(path)
            if isinstance(metadata, FileMetadata):
                return self._metadata_to_dict(metadata)
            else:
                return {"name": metadata.name, "path_display": metadata.path_display}
        except ApiError as e:
            logger.error(f"Failed to get metadata for {path}: {e}")
            raise

    def move_file(
        self,
        from_path: str,
        to_path: str,
    ) -> Dict[str, Any]:
        """
        Move a file to a different location.

        Args:
            from_path: Source file path
            to_path: Destination file path (including filename)

        Returns:
            Updated file metadata
        """
        from_path = self._normalize_path(from_path)
        to_path = self._normalize_path(to_path)

        try:
            result = self.client.files_move_v2(from_path, to_path)
            metadata = result.metadata
            if isinstance(metadata, FileMetadata):
                return self._metadata_to_dict(metadata)
            return {"path_display": metadata.path_display}
        except ApiError as e:
            logger.error(f"Failed to move {from_path} to {to_path}: {e}")
            raise

    def get_or_create_subfolder(
        self,
        parent_path: str,
        folder_name: str,
    ) -> str:
        """
        Get existing subfolder or create it.

        Args:
            parent_path: Parent folder path
            folder_name: Name of subfolder

        Returns:
            Full path to subfolder
        """
        parent = self._normalize_path(parent_path)
        folder_path = f"{parent}/{folder_name}" if parent else f"/{folder_name}"

        # Check if folder exists
        try:
            metadata = self.client.files_get_metadata(folder_path)
            if isinstance(metadata, FolderMetadata):
                return folder_path
        except ApiError as e:
            if not (e.error.is_path() and e.error.get_path().is_not_found()):
                raise

        # Create folder
        try:
            result = self.client.files_create_folder_v2(folder_path)
            logger.info(f"Created subfolder '{folder_name}' in Dropbox")
            return result.metadata.path_display
        except ApiError as e:
            # Handle race condition where folder was created between check and create
            if e.error.is_path() and e.error.get_path().is_conflict():
                return folder_path
            raise

    def get_shared_link(self, file_path: str) -> str:
        """
        Get or create a shared link for a file.

        Args:
            file_path: Path to file

        Returns:
            Shared link URL
        """
        path = self._normalize_path(file_path)

        try:
            # Try to get existing link
            links = self.client.sharing_list_shared_links(path=path).links
            if links:
                return links[0].url

            # Create new link
            settings = dropbox.sharing.SharedLinkSettings(
                requested_visibility=dropbox.sharing.RequestedVisibility.public
            )
            link = self.client.sharing_create_shared_link_with_settings(
                path, settings=settings
            )
            return link.url

        except ApiError as e:
            logger.error(f"Failed to get shared link for {path}: {e}")
            return ""


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    print("Dropbox Service Test")
    print("=" * 50)

    service = DropboxService()

    # Test authentication
    try:
        account = service.client.users_get_current_account()
        print(f"\nAuthenticated as: {account.email}")
        print(f"Display name: {account.name.display_name}")
        print("Dropbox service is working!")

        # List files in root
        print("\nFiles in app folder root:")
        files = service.list_files("")
        if files:
            for f in files[:5]:  # Show first 5
                print(f"  - {f['name']} ({f['size']} bytes)")
            if len(files) > 5:
                print(f"  ... and {len(files) - 5} more")
        else:
            print("  (no files)")

    except Exception as e:
        print(f"\nError: {e}")
        print("Make sure you have valid Dropbox credentials.")
        sys.exit(1)
