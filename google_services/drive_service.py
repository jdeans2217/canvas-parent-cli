#!/usr/bin/env python3
"""
Google Drive Service - List and download files from Google Drive.

Provides Drive API operations for scanning workflow.
"""

import io
import logging
from typing import Optional, List, Dict, Any

from googleapiclient.http import MediaIoBaseDownload

from google_services.auth import GoogleAuth

logger = logging.getLogger(__name__)

# Supported MIME types for scanning
SUPPORTED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
}

# Google Drive folder MIME type
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


class DriveService:
    """
    Google Drive API service wrapper.

    Provides methods for listing, downloading, and moving files
    in Google Drive folders.
    """

    def __init__(self, auth: Optional[GoogleAuth] = None):
        """
        Initialize Drive service.

        Args:
            auth: GoogleAuth instance (creates one if not provided)
        """
        self._auth = auth or GoogleAuth()
        self._service = None

    @property
    def service(self):
        """Get the Drive API service (lazy load)."""
        if self._service is None:
            self._service = self._auth.get_service("drive")
        return self._service

    def list_files(
        self,
        folder_id: str,
        mime_types: Optional[List[str]] = None,
        page_size: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List files in a Drive folder.

        Args:
            folder_id: Google Drive folder ID
            mime_types: Filter to specific MIME types (default: images + PDFs)
            page_size: Results per page

        Returns:
            List of file metadata dicts
        """
        if mime_types is None:
            mime_types = list(SUPPORTED_MIME_TYPES.keys())

        # Build MIME type query
        mime_query = " or ".join(f"mimeType='{mt}'" for mt in mime_types)
        query = f"'{folder_id}' in parents and ({mime_query}) and trashed=false"

        files = []
        page_token = None

        while True:
            response = self.service.files().list(
                q=query,
                spaces="drive",
                fields="nextPageToken, files(id, name, mimeType, size, createdTime, modifiedTime)",
                pageToken=page_token,
                pageSize=page_size,
                orderBy="createdTime desc",
            ).execute()

            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken")

            if not page_token:
                break

        return files

    def download_file(self, file_id: str) -> bytes:
        """
        Download file content from Drive.

        Args:
            file_id: Google Drive file ID

        Returns:
            File content as bytes
        """
        request = self.service.files().get_media(fileId=file_id)
        file_content = io.BytesIO()

        downloader = MediaIoBaseDownload(file_content, request)
        done = False

        while not done:
            status, done = downloader.next_chunk()

        return file_content.getvalue()

    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """
        Get file metadata.

        Args:
            file_id: Google Drive file ID

        Returns:
            File metadata dict
        """
        return self.service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, size, createdTime, modifiedTime, webViewLink, parents",
        ).execute()

    def move_file(
        self,
        file_id: str,
        dest_folder_id: str,
        source_folder_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Move a file to a different folder.

        Args:
            file_id: File ID to move
            dest_folder_id: Destination folder ID
            source_folder_id: Source folder ID (auto-detected if not provided)

        Returns:
            Updated file metadata
        """
        if source_folder_id is None:
            # Get current parents
            file = self.service.files().get(
                fileId=file_id,
                fields="parents"
            ).execute()
            source_folder_id = ",".join(file.get("parents", []))

        return self.service.files().update(
            fileId=file_id,
            addParents=dest_folder_id,
            removeParents=source_folder_id,
            fields="id, name, parents",
        ).execute()

    def get_or_create_subfolder(
        self,
        parent_folder_id: str,
        folder_name: str,
    ) -> str:
        """
        Get existing subfolder or create it.

        Args:
            parent_folder_id: Parent folder ID
            folder_name: Name of subfolder

        Returns:
            Subfolder ID
        """
        # Check if folder exists
        query = (
            f"'{parent_folder_id}' in parents and "
            f"name='{folder_name}' and "
            f"mimeType='{FOLDER_MIME_TYPE}' and "
            f"trashed=false"
        )

        response = self.service.files().list(
            q=query,
            spaces="drive",
            fields="files(id, name)",
        ).execute()

        files = response.get("files", [])
        if files:
            return files[0]["id"]

        # Create folder
        folder_metadata = {
            "name": folder_name,
            "mimeType": FOLDER_MIME_TYPE,
            "parents": [parent_folder_id],
        }

        folder = self.service.files().create(
            body=folder_metadata,
            fields="id",
        ).execute()

        logger.info(f"Created subfolder '{folder_name}' in Drive")
        return folder["id"]

    def get_web_view_link(self, file_id: str) -> str:
        """Get the web view URL for a file."""
        file = self.service.files().get(
            fileId=file_id,
            fields="webViewLink",
        ).execute()
        return file.get("webViewLink", "")


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    print("Drive Service Test")
    print("=" * 50)

    drive = DriveService()

    # Test authentication
    try:
        # List some files from root
        about = drive.service.about().get(fields="user").execute()
        print(f"\nAuthenticated as: {about['user']['emailAddress']}")
        print("Drive service is working!")
    except Exception as e:
        print(f"\nError: {e}")
        print("Make sure you have valid Google credentials.")
        sys.exit(1)
