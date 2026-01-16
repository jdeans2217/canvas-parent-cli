#!/usr/bin/env python3
"""
Notifications - Send alerts for documents needing manual assignment.

Sends email notifications with document preview and one-click assignment links.
"""

import logging
import hashlib
import hmac
import base64
from datetime import datetime
from typing import Optional, List

from config import get_config
from database.models import Student, ScannedDocument
from database.connection import get_session
from google_services.gmail_service import GmailService

logger = logging.getLogger(__name__)

# Secret key for signing tokens (should be in .env in production)
TOKEN_SECRET = "canvas-parent-cli-secret-key"


def generate_assign_token(document_id: int) -> str:
    """
    Generate a signed token for document assignment.

    Args:
        document_id: Database ID of the document

    Returns:
        URL-safe base64 encoded signed token
    """
    message = f"assign:{document_id}:{datetime.now().date().isoformat()}"
    signature = hmac.new(
        TOKEN_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).digest()
    token = base64.urlsafe_b64encode(
        f"{document_id}:{base64.urlsafe_b64encode(signature).decode()}".encode()
    ).decode()
    return token


def verify_assign_token(token: str) -> Optional[int]:
    """
    Verify a signed assignment token.

    Args:
        token: The token to verify

    Returns:
        Document ID if valid, None otherwise
    """
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        doc_id_str, sig_b64 = decoded.split(":", 1)
        doc_id = int(doc_id_str)

        # Verify signature (check today and yesterday for timezone issues)
        for date_offset in [0, -1]:
            from datetime import timedelta
            check_date = (datetime.now() + timedelta(days=date_offset)).date()
            message = f"assign:{doc_id}:{check_date.isoformat()}"
            expected_sig = hmac.new(
                TOKEN_SECRET.encode(),
                message.encode(),
                hashlib.sha256
            ).digest()
            if base64.urlsafe_b64encode(expected_sig).decode() == sig_b64:
                return doc_id

        return None
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        return None


def build_assignment_email(
    document: ScannedDocument,
    students: List[Student],
    base_url: str,
) -> dict:
    """
    Build email content for assignment notification.

    Args:
        document: The ScannedDocument needing assignment
        students: List of possible students to assign to
        base_url: Base URL for assignment links

    Returns:
        Dict with 'subject', 'html', and 'text' keys
    """
    token = generate_assign_token(document.id)

    # Build preview from OCR text
    preview_text = ""
    if document.ocr_text:
        lines = document.ocr_text.strip().split("\n")[:10]
        preview_text = "\n".join(lines)
        if len(document.ocr_text.split("\n")) > 10:
            preview_text += "\n..."

    # Build detected info section
    detected_info = []
    if document.detected_title:
        detected_info.append(f"Title: {document.detected_title}")
    if document.detected_date:
        detected_info.append(f"Date: {document.detected_date.strftime('%Y-%m-%d')}")
    if document.detected_score is not None:
        score_str = f"{document.detected_score}"
        if document.detected_max_score:
            score_str += f"/{document.detected_max_score}"
        detected_info.append(f"Score: {score_str}")

    detected_section = "\n".join(f"  • {info}" for info in detected_info) if detected_info else "  No information detected"

    # Build assignment links
    links_html = []
    links_text = []
    for student in students:
        url = f"{base_url}/assign/{token}/{student.id}"
        links_html.append(f'<a href="{url}" style="display:inline-block;padding:10px 20px;background:#4CAF50;color:white;text-decoration:none;border-radius:5px;margin:5px;">Assign to {student.name}</a>')
        links_text.append(f"  → Assign to {student.name}: {url}")

    # Plain text version
    text_content = f"""A scanned document couldn't be automatically assigned to a student.

File: {document.file_name}
Scanned: {document.scan_date.strftime('%Y-%m-%d %H:%M') if document.scan_date else 'Unknown'}

Detected Information:
{detected_section}

Preview:
{preview_text if preview_text else '  [No text extracted]'}

Please click to assign:
{chr(10).join(links_text)}

Or reply to this email with the student's name.
"""

    # HTML version
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        .preview {{ background: #fafafa; padding: 15px; border-left: 3px solid #ddd; margin: 15px 0; font-family: monospace; white-space: pre-wrap; }}
        .detected {{ background: #e8f5e9; padding: 15px; border-radius: 5px; margin: 15px 0; }}
        .buttons {{ margin: 20px 0; text-align: center; }}
        .footer {{ font-size: 12px; color: #666; margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2 style="margin:0;color:#333;">📄 Homework Scan Needs Assignment</h2>
            <p style="margin:10px 0 0;color:#666;">A scanned document couldn't be automatically assigned to a student.</p>
        </div>

        <p><strong>File:</strong> {document.file_name}<br>
        <strong>Scanned:</strong> {document.scan_date.strftime('%Y-%m-%d %H:%M') if document.scan_date else 'Unknown'}</p>

        <div class="detected">
            <strong>Detected Information:</strong><br>
            {detected_section.replace(chr(10), '<br>')}
        </div>

        <div class="preview">
            <strong>Document Preview:</strong><br><br>
            {preview_text if preview_text else '<em>[No text extracted]</em>'}
        </div>

        <div class="buttons">
            <p><strong>Click to assign:</strong></p>
            {' '.join(links_html)}
        </div>

        <p style="text-align:center;color:#666;">Or reply to this email with the student's name.</p>

        <div class="footer">
            <p>This notification was sent by Canvas Parent CLI.<br>
            Document ID: {document.id}</p>
        </div>
    </div>
</body>
</html>
"""

    return {
        "subject": f"Homework scan needs assignment: {document.file_name}",
        "html": html_content,
        "text": text_content,
    }


def send_assignment_notification(
    document: ScannedDocument,
    recipient_email: str = None,
) -> bool:
    """
    Send email notification for a document needing assignment.

    Args:
        document: The ScannedDocument needing assignment
        recipient_email: Email to send to (uses config if not specified)

    Returns:
        True if sent successfully, False otherwise
    """
    config = get_config()
    recipient = recipient_email or config.drive.notification_email

    if not recipient:
        logger.warning("No notification email configured")
        return False

    try:
        # Get all students
        session = get_session()
        students = session.query(Student).all()

        if not students:
            logger.warning("No students in database")
            return False

        # Build email
        email_content = build_assignment_email(
            document=document,
            students=students,
            base_url=config.drive.assign_base_url,
        )

        # Send via Gmail
        gmail = GmailService()
        gmail.send_html_email(
            to=recipient,
            subject=email_content["subject"],
            html_body=email_content["html"],
            text_body=email_content["text"],
        )

        logger.info(f"Sent assignment notification for document {document.id} to {recipient}")
        return True

    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
        return False


def send_pending_notifications() -> int:
    """
    Send notifications for all pending documents.

    Returns:
        Number of notifications sent
    """
    session = get_session()

    # Find documents without student assignment
    pending_docs = session.query(ScannedDocument).filter(
        ScannedDocument.student_id.is_(None)
    ).all()

    sent_count = 0
    for doc in pending_docs:
        if send_assignment_notification(doc):
            sent_count += 1

    return sent_count


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    print("Notification System Test")
    print("=" * 50)

    # Test token generation/verification
    test_doc_id = 123
    token = generate_assign_token(test_doc_id)
    print(f"\nGenerated token for doc {test_doc_id}: {token[:30]}...")

    verified_id = verify_assign_token(token)
    print(f"Verified token: doc_id = {verified_id}")
    print(f"Token valid: {verified_id == test_doc_id}")

    # Show config
    config = get_config()
    print(f"\nNotification email: {config.drive.notification_email or 'NOT SET'}")
    print(f"Assignment base URL: {config.drive.assign_base_url}")
