#!/usr/bin/env python3
"""
Email Processor - Process homework photos from Gmail attachments.

Monitors Gmail inbox for emails with image attachments,
processes them through OCR, and stores results in the database.
"""

import os
import base64
import logging
import tempfile
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from pathlib import Path

from sqlalchemy.orm import Session

from google_services.auth import GoogleAuth
from database.models import Student, ScannedDocument
from database.connection import get_session
from .ocr import MistralOCR, OCRResult
from .parser import GradeParser, ParsedDocument
from .matcher import AssignmentMatcher, MatchResult

logger = logging.getLogger(__name__)

# Supported image MIME types
SUPPORTED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
    "application/pdf",
}

# Gmail label for processed emails
PROCESSED_LABEL = "Canvas-Processed"


@dataclass
class EmailAttachment:
    """Represents an email attachment."""
    filename: str
    mime_type: str
    size: int
    data: bytes
    message_id: str
    subject: str
    sender: str
    received_date: datetime


@dataclass
class ProcessingResult:
    """Result of processing an email attachment."""
    attachment: EmailAttachment
    ocr_result: Optional[OCRResult]
    parsed: Optional[ParsedDocument]
    match: Optional[MatchResult]
    document_id: Optional[int]  # Database ID if saved
    success: bool
    error: Optional[str] = None


class EmailProcessor:
    """
    Processes homework photos received via email.

    Workflow:
    1. Fetch unread emails with image attachments
    2. Download and process images through Mistral OCR
    3. Parse extracted text for grades/assignment info
    4. Match to Canvas assignments
    5. Store in database
    6. Mark email as processed
    """

    def __init__(
        self,
        auth: Optional[GoogleAuth] = None,
        ocr: Optional[MistralOCR] = None,
        session: Optional[Session] = None,
    ):
        """
        Initialize the email processor.

        Args:
            auth: GoogleAuth instance
            ocr: MistralOCR instance
            session: Database session
        """
        self._auth = auth or GoogleAuth()
        self._ocr = ocr
        self._session = session
        self._gmail = None
        self._parser = GradeParser()

    @property
    def gmail(self):
        """Get Gmail API service."""
        if self._gmail is None:
            self._gmail = self._auth.get_service("gmail")
        return self._gmail

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

    def get_unread_with_attachments(
        self,
        query: str = "",
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get unread emails with image attachments.

        Args:
            query: Additional Gmail search query
            max_results: Maximum number of emails to return

        Returns:
            List of email message data
        """
        # Build search query
        search_query = "is:unread has:attachment"
        if query:
            search_query += f" {query}"

        # Exclude already processed emails
        search_query += f" -label:{PROCESSED_LABEL}"

        try:
            results = self.gmail.users().messages().list(
                userId="me",
                q=search_query,
                maxResults=max_results,
            ).execute()

            messages = results.get("messages", [])
            return messages

        except Exception as e:
            logger.error(f"Failed to fetch emails: {e}")
            return []

    def get_attachments(self, message_id: str) -> List[EmailAttachment]:
        """
        Get image/PDF attachments from a message.

        Args:
            message_id: Gmail message ID

        Returns:
            List of EmailAttachment objects
        """
        attachments = []

        try:
            message = self.gmail.users().messages().get(
                userId="me",
                id=message_id,
                format="full",
            ).execute()

            # Get message metadata
            headers = {h["name"]: h["value"] for h in message["payload"].get("headers", [])}
            subject = headers.get("Subject", "No Subject")
            sender = headers.get("From", "Unknown")
            date_str = headers.get("Date", "")

            # Parse date
            try:
                # Handle various date formats
                from email.utils import parsedate_to_datetime
                received_date = parsedate_to_datetime(date_str)
            except (ValueError, TypeError):
                received_date = datetime.now()

            # Find attachments
            parts = self._get_all_parts(message["payload"])

            for part in parts:
                mime_type = part.get("mimeType", "")
                filename = part.get("filename", "")
                body = part.get("body", {})
                attachment_id = body.get("attachmentId")
                size = body.get("size", 0)

                # Check if it's a supported attachment
                if not filename or not attachment_id:
                    continue

                if mime_type not in SUPPORTED_MIME_TYPES:
                    # Check file extension as fallback
                    ext = Path(filename).suffix.lower()
                    if ext not in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf"]:
                        continue

                # Download attachment
                attachment_data = self.gmail.users().messages().attachments().get(
                    userId="me",
                    messageId=message_id,
                    id=attachment_id,
                ).execute()

                data = base64.urlsafe_b64decode(attachment_data["data"])

                attachments.append(EmailAttachment(
                    filename=filename,
                    mime_type=mime_type,
                    size=size,
                    data=data,
                    message_id=message_id,
                    subject=subject,
                    sender=sender,
                    received_date=received_date,
                ))

        except Exception as e:
            logger.error(f"Failed to get attachments from message {message_id}: {e}")

        return attachments

    def _get_all_parts(self, payload: Dict) -> List[Dict]:
        """Recursively get all parts from a message payload."""
        parts = []

        if "parts" in payload:
            for part in payload["parts"]:
                parts.extend(self._get_all_parts(part))
        else:
            parts.append(payload)

        return parts

    def process_attachment(
        self,
        attachment: EmailAttachment,
        student_id: int,
        save_to_disk: Optional[str] = None,
    ) -> ProcessingResult:
        """
        Process a single attachment through OCR and matching.

        Args:
            attachment: EmailAttachment to process
            student_id: Student's database ID for matching
            save_to_disk: Optional directory to save processed files

        Returns:
            ProcessingResult with all extracted data
        """
        logger.info(f"Processing attachment: {attachment.filename}")

        try:
            # Run OCR
            if attachment.mime_type.startswith("image/"):
                ocr_result = self.ocr.process_image_bytes(
                    attachment.data,
                    attachment.filename,
                    attachment.mime_type,
                )
            else:
                # For PDFs, save to temp file first
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                    f.write(attachment.data)
                    temp_path = f.name

                try:
                    ocr_result = self.ocr.process_file(temp_path)
                finally:
                    os.unlink(temp_path)

            if not ocr_result.success:
                return ProcessingResult(
                    attachment=attachment,
                    ocr_result=ocr_result,
                    parsed=None,
                    match=None,
                    document_id=None,
                    success=False,
                    error=ocr_result.error,
                )

            # Parse OCR text
            parsed = self._parser.parse(ocr_result.full_text)

            # Match to assignment
            matcher = AssignmentMatcher(self.session)
            match = matcher.find_match(parsed, student_id)

            # Save to database
            document_id = self._save_to_database(
                attachment=attachment,
                ocr_result=ocr_result,
                parsed=parsed,
                match=match,
                student_id=student_id,
            )

            # Optionally save files to disk
            if save_to_disk:
                self._save_files(save_to_disk, attachment, ocr_result)

            return ProcessingResult(
                attachment=attachment,
                ocr_result=ocr_result,
                parsed=parsed,
                match=match,
                document_id=document_id,
                success=True,
            )

        except Exception as e:
            logger.error(f"Failed to process {attachment.filename}: {e}")
            return ProcessingResult(
                attachment=attachment,
                ocr_result=None,
                parsed=None,
                match=None,
                document_id=None,
                success=False,
                error=str(e),
            )

    def _save_to_database(
        self,
        attachment: EmailAttachment,
        ocr_result: OCRResult,
        parsed: ParsedDocument,
        match: MatchResult,
        student_id: int,
    ) -> int:
        """Save processed document to database."""
        doc = ScannedDocument(
            student_id=student_id,
            assignment_id=match.assignment.id if match.assignment else None,
            file_path="",  # Email attachment, no local path
            file_name=attachment.filename,
            file_size=attachment.size,
            mime_type=attachment.mime_type,
            scan_date=attachment.received_date,
            source="email",
            ocr_text=ocr_result.full_text,
            detected_title=parsed.title,
            detected_date=parsed.date,
            detected_score=parsed.score.earned if parsed.score else None,
            detected_max_score=parsed.score.possible if parsed.score else None,
            match_confidence=match.confidence,
            match_method=match.method,
        )

        # Check for grade discrepancy
        if match.assignment and match.assignment.score is not None:
            doc.canvas_score = match.assignment.score
            if parsed.score and parsed.score.earned:
                doc.score_discrepancy = parsed.score.earned - match.assignment.score

        self.session.add(doc)
        self.session.commit()

        return doc.id

    def _save_files(
        self,
        output_dir: str,
        attachment: EmailAttachment,
        ocr_result: OCRResult,
    ):
        """Save attachment and OCR text to disk."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Save original attachment
        attachment_path = output_path / attachment.filename
        with open(attachment_path, "wb") as f:
            f.write(attachment.data)

        # Save OCR text
        text_path = output_path / f"{Path(attachment.filename).stem}_ocr.txt"
        with open(text_path, "w") as f:
            f.write(ocr_result.full_text)

    def mark_as_processed(self, message_id: str):
        """Mark an email as processed by adding a label."""
        try:
            # Create label if it doesn't exist
            self._ensure_label_exists()

            # Get label ID
            labels = self.gmail.users().labels().list(userId="me").execute()
            label_id = None
            for label in labels.get("labels", []):
                if label["name"] == PROCESSED_LABEL:
                    label_id = label["id"]
                    break

            if label_id:
                # Add label to message
                self.gmail.users().messages().modify(
                    userId="me",
                    id=message_id,
                    body={"addLabelIds": [label_id]},
                ).execute()

        except Exception as e:
            logger.warning(f"Failed to mark message as processed: {e}")

    def _ensure_label_exists(self):
        """Create the processed label if it doesn't exist."""
        try:
            labels = self.gmail.users().labels().list(userId="me").execute()
            for label in labels.get("labels", []):
                if label["name"] == PROCESSED_LABEL:
                    return  # Label exists

            # Create label
            self.gmail.users().labels().create(
                userId="me",
                body={
                    "name": PROCESSED_LABEL,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            ).execute()

        except Exception as e:
            logger.warning(f"Failed to create label: {e}")

    def process_inbox(
        self,
        student_id: int,
        query: str = "",
        max_emails: int = 10,
        save_to_disk: Optional[str] = None,
        mark_processed: bool = True,
    ) -> List[ProcessingResult]:
        """
        Process all unread emails with attachments.

        Args:
            student_id: Student's database ID
            query: Additional Gmail search query
            max_emails: Maximum emails to process
            save_to_disk: Optional directory to save files
            mark_processed: Whether to mark emails as processed

        Returns:
            List of ProcessingResults
        """
        results = []

        # Get unread emails
        messages = self.get_unread_with_attachments(query, max_emails)
        logger.info(f"Found {len(messages)} unread emails with attachments")

        for msg in messages:
            message_id = msg["id"]

            # Get attachments
            attachments = self.get_attachments(message_id)

            if not attachments:
                continue

            # Process each attachment
            message_results = []
            for attachment in attachments:
                result = self.process_attachment(
                    attachment,
                    student_id,
                    save_to_disk,
                )
                message_results.append(result)
                results.append(result)

            # Mark message as processed if any attachment succeeded
            if mark_processed and any(r.success for r in message_results):
                self.mark_as_processed(message_id)

        return results


def process_homework_emails(
    student_id: int,
    query: str = "",
    max_emails: int = 10,
) -> List[ProcessingResult]:
    """
    Convenience function to process homework emails.

    Args:
        student_id: Student's database ID
        query: Additional search query
        max_emails: Max emails to process

    Returns:
        List of ProcessingResults
    """
    processor = EmailProcessor()
    return processor.process_inbox(student_id, query, max_emails)


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    print("Email Processor Test")
    print("=" * 50)

    processor = EmailProcessor()

    # Check for unread emails
    messages = processor.get_unread_with_attachments(max_results=5)
    print(f"\nFound {len(messages)} unread emails with attachments")

    if messages:
        for msg in messages[:3]:
            message_id = msg["id"]
            attachments = processor.get_attachments(message_id)

            print(f"\nMessage ID: {message_id}")
            print(f"  Attachments: {len(attachments)}")
            for att in attachments:
                print(f"    - {att.filename} ({att.mime_type}, {att.size} bytes)")
                print(f"      From: {att.sender}")
                print(f"      Subject: {att.subject}")

    else:
        print("\nNo unread emails with attachments found.")
        print("Try sending an email with a homework photo to test!")
