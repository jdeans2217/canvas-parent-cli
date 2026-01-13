#!/usr/bin/env python3
"""
Gmail Service - Send emails via Gmail API.

Provides email sending functionality for automated reports.
Supports HTML emails with embedded images and attachments.
"""

import base64
import mimetypes
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders
from typing import Optional, List, Dict, Any, Union
from pathlib import Path

from google_services.auth import GoogleAuth


class GmailService:
    """
    Gmail API service wrapper.

    Provides methods for sending plain text, HTML, and
    multipart emails with attachments.
    """

    def __init__(self, auth: Optional[GoogleAuth] = None):
        """
        Initialize Gmail service.

        Args:
            auth: GoogleAuth instance (creates one if not provided)
        """
        self._auth = auth or GoogleAuth()
        self._service = None

    @property
    def service(self):
        """Get the Gmail API service (lazy load)."""
        if self._service is None:
            self._service = self._auth.get_service("gmail")
        return self._service

    def get_user_email(self) -> Optional[str]:
        """Get the authenticated user's email address."""
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            return profile.get("emailAddress")
        except Exception:
            return None

    def send_text_email(
        self,
        to: Union[str, List[str]],
        subject: str,
        body: str,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """
        Send a plain text email.

        Args:
            to: Recipient email address(es)
            subject: Email subject
            body: Plain text body
            cc: CC recipients
            bcc: BCC recipients

        Returns:
            Gmail API response with message ID
        """
        message = MIMEText(body, "plain")
        return self._send_message(message, to, subject, cc, bcc)

    def send_html_email(
        self,
        to: Union[str, List[str]],
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None,
        embedded_images: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Send an HTML email with optional embedded images.

        Args:
            to: Recipient email address(es)
            subject: Email subject
            html_body: HTML content
            text_body: Plain text fallback (auto-generated if not provided)
            cc: CC recipients
            bcc: BCC recipients
            embedded_images: Dict of {cid: file_path} for embedded images
                Use in HTML as: <img src="cid:image_cid">

        Returns:
            Gmail API response with message ID
        """
        # Create multipart message
        if embedded_images:
            message = MIMEMultipart("related")
            msg_alternative = MIMEMultipart("alternative")
            message.attach(msg_alternative)
        else:
            message = MIMEMultipart("alternative")
            msg_alternative = message

        # Add plain text part
        if text_body is None:
            # Simple HTML stripping for fallback
            import re
            text_body = re.sub(r"<[^>]+>", "", html_body)
            text_body = re.sub(r"\s+", " ", text_body).strip()

        msg_alternative.attach(MIMEText(text_body, "plain"))
        msg_alternative.attach(MIMEText(html_body, "html"))

        # Add embedded images
        if embedded_images:
            for cid, file_path in embedded_images.items():
                if os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        img_data = f.read()

                    # Detect image type
                    mime_type, _ = mimetypes.guess_type(file_path)
                    if mime_type and mime_type.startswith("image/"):
                        subtype = mime_type.split("/")[1]
                    else:
                        subtype = "png"

                    img = MIMEImage(img_data, _subtype=subtype)
                    img.add_header("Content-ID", f"<{cid}>")
                    img.add_header(
                        "Content-Disposition", "inline", filename=os.path.basename(file_path)
                    )
                    message.attach(img)

        return self._send_message(message, to, subject, cc, bcc)

    def send_email_with_attachments(
        self,
        to: Union[str, List[str]],
        subject: str,
        body: str,
        attachments: List[str],
        html: bool = False,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """
        Send an email with file attachments.

        Args:
            to: Recipient email address(es)
            subject: Email subject
            body: Email body (HTML or plain text)
            attachments: List of file paths to attach
            html: If True, body is treated as HTML
            cc: CC recipients
            bcc: BCC recipients

        Returns:
            Gmail API response with message ID
        """
        message = MIMEMultipart("mixed")

        # Add body
        if html:
            content_part = MIMEMultipart("alternative")
            # Strip HTML for plain text version
            import re
            text_body = re.sub(r"<[^>]+>", "", body)
            text_body = re.sub(r"\s+", " ", text_body).strip()
            content_part.attach(MIMEText(text_body, "plain"))
            content_part.attach(MIMEText(body, "html"))
            message.attach(content_part)
        else:
            message.attach(MIMEText(body, "plain"))

        # Add attachments
        for file_path in attachments:
            if not os.path.exists(file_path):
                continue

            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = "application/octet-stream"

            main_type, sub_type = mime_type.split("/", 1)

            with open(file_path, "rb") as f:
                attachment = MIMEBase(main_type, sub_type)
                attachment.set_payload(f.read())

            encoders.encode_base64(attachment)
            attachment.add_header(
                "Content-Disposition",
                "attachment",
                filename=os.path.basename(file_path),
            )
            message.attach(attachment)

        return self._send_message(message, to, subject, cc, bcc)

    def _send_message(
        self,
        message: MIMEBase,
        to: Union[str, List[str]],
        subject: str,
        cc: Optional[Union[str, List[str]]] = None,
        bcc: Optional[Union[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """
        Internal method to send a MIME message.

        Args:
            message: MIME message object
            to: Recipient(s)
            subject: Subject line
            cc: CC recipients
            bcc: BCC recipients

        Returns:
            Gmail API response
        """
        # Get sender email
        sender = self.get_user_email()
        if not sender:
            raise RuntimeError("Could not determine sender email address")

        # Normalize recipients to comma-separated strings
        if isinstance(to, list):
            to = ", ".join(to)
        if isinstance(cc, list):
            cc = ", ".join(cc)
        if isinstance(bcc, list):
            bcc = ", ".join(bcc)

        # Set headers
        message["From"] = sender
        message["To"] = to
        message["Subject"] = subject

        if cc:
            message["Cc"] = cc
        if bcc:
            message["Bcc"] = bcc

        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        # Send via Gmail API
        try:
            result = (
                self.service.users()
                .messages()
                .send(userId="me", body={"raw": raw_message})
                .execute()
            )
            return result
        except Exception as e:
            raise RuntimeError(f"Failed to send email: {e}")


def send_report_email(
    to: Union[str, List[str]],
    subject: str,
    html_content: str,
    chart_images: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Convenience function to send a report email.

    Args:
        to: Recipient email address(es)
        subject: Email subject
        html_content: HTML report content
        chart_images: Dict of {cid: file_path} for embedded charts

    Returns:
        Gmail API response
    """
    gmail = GmailService()
    return gmail.send_html_email(
        to=to,
        subject=subject,
        html_body=html_content,
        embedded_images=chart_images,
    )


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    print("Gmail Service Test")
    print("=" * 50)

    gmail = GmailService()

    # Check authentication
    email = gmail.get_user_email()
    if email:
        print(f"Authenticated as: {email}")

        # Send test email
        response = input(f"\nSend test email to {email}? (y/N): ").strip().lower()
        if response == "y":
            result = gmail.send_text_email(
                to=email,
                subject="Canvas Parent CLI - Test Email",
                body="This is a test email from Canvas Parent CLI.\n\nIf you received this, Gmail integration is working!",
            )
            print(f"Email sent! Message ID: {result.get('id')}")
    else:
        print("Failed to authenticate. Run google_services/auth.py first.")
