#!/usr/bin/env python3
"""
Dropbox Processor - Process scanned documents from Dropbox.

Monitors Dropbox app folder for new scans, processes them through OCR,
and stores results in the database. Supports smart student detection.
"""

import logging
import tempfile
import os
import hashlib
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List

from sqlalchemy.orm import Session

from cloud_services.dropbox_auth import DropboxAuth
from cloud_services.dropbox_service import DropboxService
from database.models import Student, ScannedDocument
from database.connection import get_session
from config import get_config
from .ocr import MistralOCR, OCRResult
from .parser import GradeParser, ParsedDocument
from .matcher import AssignmentMatcher, MatchResult
from .student_detector import StudentDetector, StudentDetection

logger = logging.getLogger(__name__)


@dataclass
class DropboxFile:
    """Represents a file from Dropbox."""
    file_path: str  # Full path in Dropbox (used as ID)
    name: str
    mime_type: str
    size: int
    created_time: datetime
    web_link: str = ""


@dataclass
class DropboxProcessingResult:
    """Result of processing a Dropbox file."""
    dropbox_file: DropboxFile
    ocr_result: Optional[OCRResult]
    parsed: Optional[ParsedDocument]
    match: Optional[MatchResult]
    student_detection: Optional[StudentDetection]
    document_id: Optional[int]  # Database ID if saved
    success: bool
    status: str = "processed"  # processed, pending, failed, duplicate
    error: Optional[str] = None
    file_hash: Optional[str] = None  # SHA256 hash of file content


class DropboxProcessor:
    """
    Processes scanned documents from Dropbox.

    Workflow:
    1. List new files in Dropbox app folder
    2. Check if file already processed (by dropbox_path in DB)
    3. Download and process through Mistral OCR
    4. Parse extracted text for grades/assignment info
    5. Detect student (smart detection for shared folders)
    6. Match to Canvas assignments
    7. Store in database with appropriate status
    8. Move file to student folder or 'Pending' folder
    """

    def __init__(
        self,
        auth: Optional[DropboxAuth] = None,
        ocr: Optional[MistralOCR] = None,
        session: Optional[Session] = None,
    ):
        """
        Initialize the Dropbox processor.

        Args:
            auth: DropboxAuth instance
            ocr: MistralOCR instance
            session: Database session
        """
        self._auth = auth or DropboxAuth()
        self._ocr = ocr
        self._session = session
        self._dropbox = None
        self._parser = GradeParser()
        self._student_detector = None

    @property
    def dropbox(self) -> DropboxService:
        """Get Dropbox service (lazy load)."""
        if self._dropbox is None:
            self._dropbox = DropboxService(self._auth)
        return self._dropbox

    @property
    def ocr(self) -> MistralOCR:
        """Get OCR instance (lazy load)."""
        if self._ocr is None:
            self._ocr = MistralOCR()
        return self._ocr

    @property
    def session(self) -> Session:
        """Get database session."""
        if self._session is None:
            self._session = get_session()
        return self._session

    @property
    def student_detector(self) -> StudentDetector:
        """Get student detector (lazy load)."""
        if self._student_detector is None:
            self._student_detector = StudentDetector(self.session)
        return self._student_detector

    def _compute_file_hash(self, content: bytes) -> str:
        """Compute SHA256 hash of file content."""
        return hashlib.sha256(content).hexdigest()

    def _check_duplicate(self, file_hash: str) -> Optional[ScannedDocument]:
        """Check if a file with this hash already exists in the database."""
        return self.session.query(ScannedDocument).filter_by(
            file_hash=file_hash
        ).first()

    def get_new_files(self, folder_path: str = "") -> List[DropboxFile]:
        """
        Get files from Dropbox folder that haven't been processed.

        Args:
            folder_path: Path within app folder (empty = root)

        Returns:
            List of DropboxFile objects for unprocessed files
        """
        # Get all files in folder
        files = self.dropbox.list_files(folder_path)

        # Filter out already processed files
        new_files = []
        for f in files:
            # Check if this path exists in database
            existing = self.session.query(ScannedDocument).filter_by(
                dropbox_path=f["path_display"]
            ).first()

            if existing is None:
                # Parse datetime
                created_str = f.get("createdTime", "")
                if created_str:
                    try:
                        created_time = datetime.fromisoformat(
                            created_str.replace("Z", "+00:00")
                        )
                    except ValueError:
                        created_time = datetime.now()
                else:
                    created_time = datetime.now()

                new_files.append(DropboxFile(
                    file_path=f["path_display"],
                    name=f["name"],
                    mime_type=f["mimeType"],
                    size=f.get("size", 0),
                    created_time=created_time,
                    web_link="",  # Will get shared link if needed
                ))

        return new_files

    def process_file_with_detection(
        self,
        dropbox_file: DropboxFile,
        source_folder: str,
        confidence_threshold: int = 70,
        move_files: bool = True,
    ) -> DropboxProcessingResult:
        """
        Process a file with smart student detection.

        Args:
            dropbox_file: DropboxFile to process
            source_folder: Source folder path
            confidence_threshold: Minimum confidence for auto-assignment
            move_files: Whether to move files after processing

        Returns:
            DropboxProcessingResult with detection and processing data
        """
        logger.info(f"Processing Dropbox file with detection: {dropbox_file.name}")

        try:
            # Download file
            file_content = self.dropbox.download_file(dropbox_file.file_path)

            # Compute hash and check for duplicates
            file_hash = self._compute_file_hash(file_content)
            existing = self._check_duplicate(file_hash)
            if existing:
                logger.info(f"Duplicate detected: {dropbox_file.name} matches existing document ID {existing.id}")
                return DropboxProcessingResult(
                    dropbox_file=dropbox_file,
                    ocr_result=None,
                    parsed=None,
                    match=None,
                    student_detection=None,
                    document_id=existing.id,
                    success=True,
                    status="duplicate",
                    error=f"Duplicate of document ID {existing.id}",
                    file_hash=file_hash,
                )

            # Process through OCR
            if dropbox_file.mime_type.startswith("image/"):
                ocr_result = self.ocr.process_image_bytes(
                    file_content,
                    dropbox_file.name,
                    dropbox_file.mime_type,
                )
            else:
                # For PDFs, save to temp file
                with tempfile.NamedTemporaryFile(
                    suffix=".pdf", delete=False
                ) as f:
                    f.write(file_content)
                    temp_path = f.name

                try:
                    ocr_result = self.ocr.process_file(temp_path)
                finally:
                    os.unlink(temp_path)

            if not ocr_result.success:
                return DropboxProcessingResult(
                    dropbox_file=dropbox_file,
                    ocr_result=ocr_result,
                    parsed=None,
                    match=None,
                    student_detection=None,
                    document_id=None,
                    success=False,
                    status="failed",
                    error=ocr_result.error,
                )

            # Parse OCR text
            parsed = self._parser.parse(ocr_result.full_text)

            # Detect student
            detection = self.student_detector.detect(parsed)

            # Determine status based on detection confidence
            if detection.is_confident and detection.confidence >= confidence_threshold:
                status = "processed"
                student_id = detection.student.id
                # Move to student's folder (use first name)
                dest_folder = detection.student.name.split()[0]
            else:
                status = "pending"
                student_id = detection.student.id if detection.student else None
                dest_folder = "Pending"

            # Match to assignment (if we have a student)
            match = None
            if student_id:
                matcher = AssignmentMatcher(self.session)
                match = matcher.find_match(parsed, student_id)

            # Get shared link for the file
            web_link = ""
            try:
                web_link = self.dropbox.get_shared_link(dropbox_file.file_path)
            except Exception as e:
                logger.warning(f"Could not get shared link: {e}")

            # Save to database
            document_id = self._save_to_database_with_detection(
                dropbox_file=dropbox_file,
                ocr_result=ocr_result,
                parsed=parsed,
                match=match,
                detection=detection,
                student_id=student_id,
                status=status,
                file_hash=file_hash,
                web_link=web_link,
            )

            # Move to appropriate folder
            if move_files:
                try:
                    # Ensure destination folder exists
                    dest_folder_path = self.dropbox.get_or_create_subfolder("", dest_folder)

                    # Build new path
                    new_path = f"{dest_folder_path}/{dropbox_file.name}"

                    self.dropbox.move_file(dropbox_file.file_path, new_path)
                    logger.info(f"Moved {dropbox_file.name} to {dest_folder} folder")
                except Exception as e:
                    logger.warning(f"Failed to move file: {e}")

            return DropboxProcessingResult(
                dropbox_file=dropbox_file,
                ocr_result=ocr_result,
                parsed=parsed,
                match=match,
                student_detection=detection,
                document_id=document_id,
                success=True,
                status=status,
                file_hash=file_hash,
            )

        except Exception as e:
            logger.error(f"Failed to process {dropbox_file.name}: {e}")
            return DropboxProcessingResult(
                dropbox_file=dropbox_file,
                ocr_result=None,
                parsed=None,
                match=None,
                student_detection=None,
                document_id=None,
                success=False,
                status="failed",
                error=str(e),
            )

    def _save_to_database_with_detection(
        self,
        dropbox_file: DropboxFile,
        ocr_result: OCRResult,
        parsed: ParsedDocument,
        match: Optional[MatchResult],
        detection: StudentDetection,
        student_id: Optional[int],
        status: str,
        file_hash: Optional[str] = None,
        web_link: str = "",
    ) -> int:
        """Save processed document to database with detection info."""
        doc = ScannedDocument(
            student_id=student_id,
            assignment_id=match.assignment.id if match and match.assignment else None,
            file_path="",
            file_name=dropbox_file.name,
            file_size=dropbox_file.size,
            mime_type=dropbox_file.mime_type,
            scan_date=dropbox_file.created_time,
            source="dropbox",
            ocr_text=ocr_result.full_text,
            detected_title=parsed.title,
            detected_date=parsed.date,
            detected_score=parsed.score.earned if parsed.score else None,
            detected_max_score=parsed.score.possible if parsed.score else None,
            match_confidence=match.confidence if match else 0,
            match_method=match.method if match else "none",
            # Dropbox-specific fields
            dropbox_path=dropbox_file.file_path,
            dropbox_url=web_link,
            # Hash for duplicate detection
            file_hash=file_hash,
            # Detection fields
            status=status,
            detection_confidence=detection.confidence,
            detection_method=detection.method,
        )

        # Check for grade discrepancy
        if match and match.assignment and match.assignment.score is not None:
            doc.canvas_score = match.assignment.score
            if parsed.score and parsed.score.earned:
                doc.score_discrepancy = parsed.score.earned - match.assignment.score

        self.session.add(doc)
        self.session.commit()

        return doc.id

    def process_folder(
        self,
        folder_path: str = "",
        confidence_threshold: int = 70,
        move_files: bool = True,
    ) -> List[DropboxProcessingResult]:
        """
        Process all new files in a Dropbox folder with smart detection.

        Args:
            folder_path: Folder path (empty = app folder root)
            confidence_threshold: Minimum confidence for auto-assignment
            move_files: Whether to move files after processing

        Returns:
            List of DropboxProcessingResults
        """
        results = []

        # Get new files
        new_files = self.get_new_files(folder_path)
        logger.info(f"Found {len(new_files)} new files to process")

        # Process each file with detection
        for dropbox_file in new_files:
            result = self.process_file_with_detection(
                dropbox_file=dropbox_file,
                source_folder=folder_path,
                confidence_threshold=confidence_threshold,
                move_files=move_files,
            )
            results.append(result)

        return results

    def get_pending_documents(self) -> List[ScannedDocument]:
        """Get all documents with pending status from Dropbox."""
        return self.session.query(ScannedDocument).filter(
            ScannedDocument.source == "dropbox",
            ScannedDocument.student_id.is_(None)
        ).all()


def process_dropbox_scans(
    folder_path: str = "",
    move_to_processed: bool = True,
) -> List[DropboxProcessingResult]:
    """
    Convenience function to process Dropbox folder.

    Args:
        folder_path: Folder path within app folder (empty = root)
        move_to_processed: Whether to move processed files

    Returns:
        List of DropboxProcessingResults
    """
    config = get_config()
    processor = DropboxProcessor()

    return processor.process_folder(
        folder_path=folder_path or config.dropbox.scan_folder,
        confidence_threshold=config.dropbox.confidence_threshold,
        move_files=move_to_processed,
    )


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    print("Dropbox Processor Test")
    print("=" * 50)

    config = get_config()

    if not config.dropbox.is_valid():
        print("\nDropbox not configured.")
        print("Set DROPBOX_APP_KEY and DROPBOX_APP_SECRET in .env")
        sys.exit(1)

    folder_path = sys.argv[1] if len(sys.argv) > 1 else config.dropbox.scan_folder

    processor = DropboxProcessor()

    # List files in folder
    print(f"\nListing files in: {folder_path or '(root)'}")
    new_files = processor.get_new_files(folder_path)

    if not new_files:
        print("No new files to process.")
    else:
        print(f"Found {len(new_files)} new files:")
        for f in new_files:
            print(f"  - {f.name} ({f.mime_type}, {f.size} bytes)")

        print("\nProcessing with smart student detection...")
