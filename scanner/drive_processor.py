#!/usr/bin/env python3
"""
Drive Processor - Process scanned documents from Google Drive.

Monitors Drive folders for new scans, processes them through OCR,
and stores results in the database. Supports both per-student folders
and shared folder with smart student detection.
"""

import logging
import tempfile
import os
import hashlib
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List

from sqlalchemy.orm import Session

from google_services.auth import GoogleAuth
from google_services.drive_service import DriveService, SUPPORTED_MIME_TYPES
from database.models import Student, ScannedDocument
from database.connection import get_session
from config import get_config
from .ocr import MistralOCR, OCRResult
from .parser import GradeParser, ParsedDocument
from .matcher import AssignmentMatcher, MatchResult
from .student_detector import StudentDetector, StudentDetection

logger = logging.getLogger(__name__)


@dataclass
class DriveFile:
    """Represents a file from Google Drive."""
    file_id: str
    name: str
    mime_type: str
    size: int
    created_time: datetime
    web_view_link: str


@dataclass
class DriveProcessingResult:
    """Result of processing a Drive file."""
    drive_file: DriveFile
    ocr_result: Optional[OCRResult]
    parsed: Optional[ParsedDocument]
    match: Optional[MatchResult]
    student_detection: Optional[StudentDetection]
    document_id: Optional[int]  # Database ID if saved
    success: bool
    status: str = "processed"  # processed, pending, failed, duplicate
    error: Optional[str] = None
    file_hash: Optional[str] = None  # SHA256 hash of file content


class DriveProcessor:
    """
    Processes scanned documents from Google Drive.

    Workflow:
    1. List new files in Drive folder
    2. Check if file already processed (by drive_file_id in DB)
    3. Download and process through Mistral OCR
    4. Parse extracted text for grades/assignment info
    5. Detect student (smart detection for shared folders)
    6. Match to Canvas assignments
    7. Store in database with appropriate status
    8. Move file to 'Processed' or 'Pending' subfolder
    """

    def __init__(
        self,
        auth: Optional[GoogleAuth] = None,
        ocr: Optional[MistralOCR] = None,
        session: Optional[Session] = None,
    ):
        """
        Initialize the Drive processor.

        Args:
            auth: GoogleAuth instance
            ocr: MistralOCR instance
            session: Database session
        """
        self._auth = auth or GoogleAuth()
        self._ocr = ocr
        self._session = session
        self._drive = None
        self._parser = GradeParser()
        self._student_detector = None

    @property
    def drive(self) -> DriveService:
        """Get Drive service (lazy load)."""
        if self._drive is None:
            self._drive = DriveService(self._auth)
        return self._drive

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
        """
        Check if a file with this hash already exists in the database.

        Args:
            file_hash: SHA256 hash of file content

        Returns:
            Existing ScannedDocument if duplicate found, None otherwise
        """
        return self.session.query(ScannedDocument).filter_by(
            file_hash=file_hash
        ).first()

    def get_new_files(self, folder_id: str) -> List[DriveFile]:
        """
        Get files from Drive folder that haven't been processed.

        Args:
            folder_id: Google Drive folder ID

        Returns:
            List of DriveFile objects for unprocessed files
        """
        # Get all files in folder
        files = self.drive.list_files(folder_id)

        # Filter out already processed files
        new_files = []
        for f in files:
            # Check if this file_id exists in database
            existing = self.session.query(ScannedDocument).filter_by(
                drive_file_id=f["id"]
            ).first()

            if existing is None:
                # Parse datetime
                created_str = f.get("createdTime", "")
                if created_str:
                    created_time = datetime.fromisoformat(
                        created_str.replace("Z", "+00:00")
                    )
                else:
                    created_time = datetime.now()

                new_files.append(DriveFile(
                    file_id=f["id"],
                    name=f["name"],
                    mime_type=f["mimeType"],
                    size=int(f.get("size", 0)),
                    created_time=created_time,
                    web_view_link=self.drive.get_web_view_link(f["id"]),
                ))

        return new_files

    def process_file_with_detection(
        self,
        drive_file: DriveFile,
        folder_id: str,
        confidence_threshold: int = 70,
        move_files: bool = True,
    ) -> DriveProcessingResult:
        """
        Process a file with smart student detection.

        Args:
            drive_file: DriveFile to process
            folder_id: Source folder ID
            confidence_threshold: Minimum confidence for auto-assignment
            move_files: Whether to move files after processing

        Returns:
            DriveProcessingResult with detection and processing data
        """
        logger.info(f"Processing Drive file with detection: {drive_file.name}")

        try:
            # Download file
            file_content = self.drive.download_file(drive_file.file_id)

            # Compute hash and check for duplicates
            file_hash = self._compute_file_hash(file_content)
            existing = self._check_duplicate(file_hash)
            if existing:
                logger.info(f"Duplicate detected: {drive_file.name} matches existing document ID {existing.id} ({existing.file_name})")
                return DriveProcessingResult(
                    drive_file=drive_file,
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
            if drive_file.mime_type.startswith("image/"):
                ocr_result = self.ocr.process_image_bytes(
                    file_content,
                    drive_file.name,
                    drive_file.mime_type,
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
                return DriveProcessingResult(
                    drive_file=drive_file,
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

            # Save to database
            document_id = self._save_to_database_with_detection(
                drive_file=drive_file,
                ocr_result=ocr_result,
                parsed=parsed,
                match=match,
                detection=detection,
                student_id=student_id,
                status=status,
                file_hash=file_hash,
            )

            # Move to appropriate folder
            if move_files:
                try:
                    dest_folder_id = self.drive.get_or_create_subfolder(
                        folder_id, dest_folder
                    )
                    self.drive.move_file(
                        drive_file.file_id,
                        dest_folder_id,
                        folder_id,
                    )
                    logger.info(f"Moved {drive_file.name} to {dest_folder} folder")
                except Exception as e:
                    logger.warning(f"Failed to move file: {e}")

            return DriveProcessingResult(
                drive_file=drive_file,
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
            logger.error(f"Failed to process {drive_file.name}: {e}")
            return DriveProcessingResult(
                drive_file=drive_file,
                ocr_result=None,
                parsed=None,
                match=None,
                student_detection=None,
                document_id=None,
                success=False,
                status="failed",
                error=str(e),
            )

    def process_file(
        self,
        drive_file: DriveFile,
        student_id: int,
        move_to_processed: bool = True,
        processed_folder_id: Optional[str] = None,
        source_folder_id: Optional[str] = None,
    ) -> DriveProcessingResult:
        """
        Process a single file from Drive (with known student).

        Args:
            drive_file: DriveFile to process
            student_id: Student's database ID
            move_to_processed: Whether to move file after processing
            processed_folder_id: Destination folder for processed files
            source_folder_id: Source folder ID (for moving)

        Returns:
            DriveProcessingResult with all processing data
        """
        logger.info(f"Processing Drive file: {drive_file.name}")

        try:
            # Download file
            file_content = self.drive.download_file(drive_file.file_id)

            # Compute hash and check for duplicates
            file_hash = self._compute_file_hash(file_content)
            existing = self._check_duplicate(file_hash)
            if existing:
                logger.info(f"Duplicate detected: {drive_file.name} matches existing document ID {existing.id} ({existing.file_name})")
                return DriveProcessingResult(
                    drive_file=drive_file,
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
            if drive_file.mime_type.startswith("image/"):
                ocr_result = self.ocr.process_image_bytes(
                    file_content,
                    drive_file.name,
                    drive_file.mime_type,
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
                return DriveProcessingResult(
                    drive_file=drive_file,
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

            # Match to assignment
            matcher = AssignmentMatcher(self.session)
            match = matcher.find_match(parsed, student_id)

            # Save to database
            document_id = self._save_to_database(
                drive_file=drive_file,
                ocr_result=ocr_result,
                parsed=parsed,
                match=match,
                student_id=student_id,
                file_hash=file_hash,
            )

            # Move to processed folder
            if move_to_processed and processed_folder_id:
                try:
                    self.drive.move_file(
                        drive_file.file_id,
                        processed_folder_id,
                        source_folder_id,
                    )
                    logger.info(f"Moved {drive_file.name} to Processed folder")
                except Exception as e:
                    logger.warning(f"Failed to move file to processed: {e}")

            return DriveProcessingResult(
                drive_file=drive_file,
                ocr_result=ocr_result,
                parsed=parsed,
                match=match,
                student_detection=None,
                document_id=document_id,
                success=True,
                status="processed",
                file_hash=file_hash,
            )

        except Exception as e:
            logger.error(f"Failed to process {drive_file.name}: {e}")
            return DriveProcessingResult(
                drive_file=drive_file,
                ocr_result=None,
                parsed=None,
                match=None,
                student_detection=None,
                document_id=None,
                success=False,
                status="failed",
                error=str(e),
            )

    def _save_to_database(
        self,
        drive_file: DriveFile,
        ocr_result: OCRResult,
        parsed: ParsedDocument,
        match: MatchResult,
        student_id: int,
        file_hash: Optional[str] = None,
    ) -> int:
        """Save processed document to database (known student)."""
        doc = ScannedDocument(
            student_id=student_id,
            assignment_id=match.assignment.id if match.assignment else None,
            file_path="",  # No local path for Drive files
            file_name=drive_file.name,
            file_size=drive_file.size,
            mime_type=drive_file.mime_type,
            scan_date=drive_file.created_time,
            source="google_drive",
            ocr_text=ocr_result.full_text,
            detected_title=parsed.title,
            detected_date=parsed.date,
            detected_score=parsed.score.earned if parsed.score else None,
            detected_max_score=parsed.score.possible if parsed.score else None,
            match_confidence=match.confidence,
            match_method=match.method,
            # Drive-specific fields
            drive_file_id=drive_file.file_id,
            drive_url=drive_file.web_view_link,
            # Hash for duplicate detection
            file_hash=file_hash,
        )

        # Check for grade discrepancy
        if match.assignment and match.assignment.score is not None:
            doc.canvas_score = match.assignment.score
            if parsed.score and parsed.score.earned:
                doc.score_discrepancy = parsed.score.earned - match.assignment.score

        self.session.add(doc)
        self.session.commit()

        return doc.id

    def _save_to_database_with_detection(
        self,
        drive_file: DriveFile,
        ocr_result: OCRResult,
        parsed: ParsedDocument,
        match: Optional[MatchResult],
        detection: StudentDetection,
        student_id: Optional[int],
        status: str,
        file_hash: Optional[str] = None,
    ) -> int:
        """Save processed document to database with detection info."""
        doc = ScannedDocument(
            student_id=student_id,
            assignment_id=match.assignment.id if match and match.assignment else None,
            file_path="",
            file_name=drive_file.name,
            file_size=drive_file.size,
            mime_type=drive_file.mime_type,
            scan_date=drive_file.created_time,
            source="google_drive",
            ocr_text=ocr_result.full_text,
            detected_title=parsed.title,
            detected_date=parsed.date,
            detected_score=parsed.score.earned if parsed.score else None,
            detected_max_score=parsed.score.possible if parsed.score else None,
            match_confidence=match.confidence if match else 0,
            match_method=match.method if match else "none",
            # Drive-specific fields
            drive_file_id=drive_file.file_id,
            drive_url=drive_file.web_view_link,
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

    def process_shared_folder(
        self,
        folder_id: str,
        confidence_threshold: int = 70,
        move_files: bool = True,
    ) -> List[DriveProcessingResult]:
        """
        Process all new files in a shared Drive folder with smart detection.

        Args:
            folder_id: Google Drive folder ID
            confidence_threshold: Minimum confidence for auto-assignment
            move_files: Whether to move files after processing

        Returns:
            List of DriveProcessingResults
        """
        results = []

        # Get new files
        new_files = self.get_new_files(folder_id)
        logger.info(f"Found {len(new_files)} new files to process")

        # Process each file with detection
        for drive_file in new_files:
            result = self.process_file_with_detection(
                drive_file=drive_file,
                folder_id=folder_id,
                confidence_threshold=confidence_threshold,
                move_files=move_files,
            )
            results.append(result)

        return results

    def process_folder(
        self,
        folder_id: str,
        student_id: int,
        move_to_processed: bool = True,
    ) -> List[DriveProcessingResult]:
        """
        Process all new files in a student's Drive folder (known student).

        Args:
            folder_id: Google Drive folder ID
            student_id: Student's database ID
            move_to_processed: Whether to move files after processing

        Returns:
            List of DriveProcessingResults
        """
        results = []

        # Get/create processed subfolder
        processed_folder_id = None
        if move_to_processed:
            processed_folder_id = self.drive.get_or_create_subfolder(
                folder_id, "Processed"
            )

        # Get new files
        new_files = self.get_new_files(folder_id)
        logger.info(f"Found {len(new_files)} new files to process")

        # Process each file
        for drive_file in new_files:
            result = self.process_file(
                drive_file=drive_file,
                student_id=student_id,
                move_to_processed=move_to_processed,
                processed_folder_id=processed_folder_id,
                source_folder_id=folder_id,
            )
            results.append(result)

        return results

    def get_pending_documents(self) -> List[ScannedDocument]:
        """Get all documents with pending status."""
        # For now, get documents without a student_id assigned
        return self.session.query(ScannedDocument).filter(
            ScannedDocument.student_id.is_(None)
        ).all()


def process_drive_scans(
    folder_id: str,
    student_id: int = None,
    move_to_processed: bool = True,
) -> List[DriveProcessingResult]:
    """
    Convenience function to process Drive folder.

    Args:
        folder_id: Google Drive folder ID
        student_id: Student's database ID (None for shared folder with detection)
        move_to_processed: Whether to move processed files

    Returns:
        List of DriveProcessingResults
    """
    processor = DriveProcessor()

    if student_id:
        return processor.process_folder(folder_id, student_id, move_to_processed)
    else:
        config = get_config()
        return processor.process_shared_folder(
            folder_id,
            confidence_threshold=config.drive.confidence_threshold,
            move_files=move_to_processed,
        )


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    print("Drive Processor Test")
    print("=" * 50)

    # Check if a folder ID was provided
    if len(sys.argv) < 2:
        print("\nUsage: python -m scanner.drive_processor <folder_id> [student_id]")
        print("\nTo find folder ID, open the folder in Google Drive and")
        print("copy the ID from the URL: drive.google.com/drive/folders/<FOLDER_ID>")
        print("\nIf student_id is omitted, smart detection will be used.")
        sys.exit(1)

    folder_id = sys.argv[1]
    student_id = int(sys.argv[2]) if len(sys.argv) > 2 else None

    processor = DriveProcessor()

    # List files in folder
    print(f"\nListing files in folder: {folder_id}")
    new_files = processor.get_new_files(folder_id)

    if not new_files:
        print("No new files to process.")
    else:
        print(f"Found {len(new_files)} new files:")
        for f in new_files:
            print(f"  - {f.name} ({f.mime_type}, {f.size} bytes)")

        if student_id:
            print(f"\nProcessing with student_id={student_id}")
        else:
            print("\nProcessing with smart student detection")
