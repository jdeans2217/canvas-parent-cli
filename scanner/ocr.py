#!/usr/bin/env python3
"""
Mistral OCR Integration - Extract text from images and PDFs.

Uses the Mistral OCR API to process scanned homework, tests, and other documents.
Supports images (PNG, JPEG, WEBP, GIF) and PDF files.
"""

import os
import base64
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from mistralai import Mistral
from mistralai.models import File

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1
MAX_RETRY_DELAY = 32

# Supported formats
SUPPORTED_IMAGE_FORMATS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

SUPPORTED_PDF_FORMATS = {".pdf"}


@dataclass
class OCRPage:
    """Single page of OCR results."""
    page_number: int
    text: str
    markdown: str
    width: Optional[int] = None
    height: Optional[int] = None
    dpi: Optional[int] = None


@dataclass
class OCRResult:
    """Complete OCR result for a document."""
    file_path: str
    file_name: str
    file_type: str  # "image" or "pdf"
    mime_type: Optional[str] = None
    pages: List[OCRPage] = field(default_factory=list)
    total_pages: int = 0
    processing_time: float = 0.0
    file_size_kb: float = 0.0
    model: str = ""
    success: bool = True
    error: Optional[str] = None

    @property
    def full_text(self) -> str:
        """Get all text concatenated."""
        return "\n\n".join(page.text for page in self.pages)

    @property
    def full_markdown(self) -> str:
        """Get all markdown concatenated."""
        parts = []
        for page in self.pages:
            parts.append(f"## Page {page.page_number}\n\n{page.markdown}")
        return "\n\n".join(parts)


def retry_with_backoff(func):
    """Decorator for exponential backoff retry."""
    def wrapper(*args, **kwargs):
        delay = INITIAL_RETRY_DELAY
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    logger.error(f"Failed after {MAX_RETRIES} attempts: {e}")
                    raise
                delay = min(delay * 2, MAX_RETRY_DELAY)
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                time.sleep(delay)
        return None
    return wrapper


class MistralOCR:
    """
    Mistral OCR client for document text extraction.

    Usage:
        ocr = MistralOCR()
        result = ocr.process_file("/path/to/homework.jpg")
        print(result.full_text)
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Mistral OCR client.

        Args:
            api_key: Mistral API key (defaults to MISTRAL_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Mistral API key required. Set MISTRAL_API_KEY environment variable "
                "or pass api_key parameter."
            )
        self.client = Mistral(api_key=self.api_key)
        self.model = "mistral-ocr-latest"

    def process_file(self, file_path: str) -> OCRResult:
        """
        Process a file (image or PDF) with OCR.

        Args:
            file_path: Path to file to process

        Returns:
            OCRResult with extracted text and metadata
        """
        path = Path(file_path)
        if not path.exists():
            return OCRResult(
                file_path=str(path),
                file_name=path.name,
                file_type="unknown",
                success=False,
                error=f"File not found: {file_path}"
            )

        ext = path.suffix.lower()

        if ext in SUPPORTED_IMAGE_FORMATS:
            return self._process_image(path)
        elif ext in SUPPORTED_PDF_FORMATS:
            return self._process_pdf(path)
        else:
            return OCRResult(
                file_path=str(path),
                file_name=path.name,
                file_type="unknown",
                success=False,
                error=f"Unsupported format: {ext}. Supported: {list(SUPPORTED_IMAGE_FORMATS.keys()) + list(SUPPORTED_PDF_FORMATS)}"
            )

    def process_image_bytes(self, image_bytes: bytes, filename: str, mime_type: str) -> OCRResult:
        """
        Process image from bytes (useful for email attachments).

        Args:
            image_bytes: Raw image data
            filename: Original filename
            mime_type: MIME type of image

        Returns:
            OCRResult with extracted text
        """
        start_time = time.time()

        # Validate mime type
        valid_mimes = list(SUPPORTED_IMAGE_FORMATS.values())
        if mime_type not in valid_mimes:
            return OCRResult(
                file_path="",
                file_name=filename,
                file_type="image",
                mime_type=mime_type,
                success=False,
                error=f"Unsupported MIME type: {mime_type}. Supported: {valid_mimes}"
            )

        try:
            base64_image = base64.b64encode(image_bytes).decode("utf-8")

            @retry_with_backoff
            def perform_ocr():
                return self.client.ocr.process(
                    model=self.model,
                    document={
                        "type": "image_url",
                        "image_url": f"data:{mime_type};base64,{base64_image}"
                    }
                )

            response = perform_ocr()
            processing_time = time.time() - start_time

            pages = []
            for i, page in enumerate(response.pages):
                pages.append(OCRPage(
                    page_number=i + 1,
                    text=page.markdown.replace("\\", ""),
                    markdown=page.markdown,
                    width=page.dimensions.width if page.dimensions else None,
                    height=page.dimensions.height if page.dimensions else None,
                    dpi=page.dimensions.dpi if page.dimensions else None,
                ))

            return OCRResult(
                file_path="",
                file_name=filename,
                file_type="image",
                mime_type=mime_type,
                pages=pages,
                total_pages=len(pages),
                processing_time=processing_time,
                file_size_kb=len(image_bytes) / 1024,
                model=response.model,
                success=True,
            )

        except Exception as e:
            logger.error(f"OCR failed for {filename}: {e}")
            return OCRResult(
                file_path="",
                file_name=filename,
                file_type="image",
                mime_type=mime_type,
                success=False,
                error=str(e),
                processing_time=time.time() - start_time,
            )

    def _process_image(self, path: Path) -> OCRResult:
        """Process an image file."""
        start_time = time.time()
        mime_type = SUPPORTED_IMAGE_FORMATS.get(path.suffix.lower())

        logger.info(f"Processing image: {path.name} ({mime_type})")

        try:
            with open(path, "rb") as f:
                image_bytes = f.read()

            base64_image = base64.b64encode(image_bytes).decode("utf-8")

            @retry_with_backoff
            def perform_ocr():
                return self.client.ocr.process(
                    model=self.model,
                    document={
                        "type": "image_url",
                        "image_url": f"data:{mime_type};base64,{base64_image}"
                    }
                )

            response = perform_ocr()
            processing_time = time.time() - start_time

            pages = []
            for i, page in enumerate(response.pages):
                pages.append(OCRPage(
                    page_number=i + 1,
                    text=page.markdown.replace("\\", ""),
                    markdown=page.markdown,
                    width=page.dimensions.width if page.dimensions else None,
                    height=page.dimensions.height if page.dimensions else None,
                    dpi=page.dimensions.dpi if page.dimensions else None,
                ))

            return OCRResult(
                file_path=str(path),
                file_name=path.name,
                file_type="image",
                mime_type=mime_type,
                pages=pages,
                total_pages=len(pages),
                processing_time=processing_time,
                file_size_kb=path.stat().st_size / 1024,
                model=response.model,
                success=True,
            )

        except Exception as e:
            logger.error(f"Image OCR failed for {path.name}: {e}")
            return OCRResult(
                file_path=str(path),
                file_name=path.name,
                file_type="image",
                mime_type=mime_type,
                success=False,
                error=str(e),
                processing_time=time.time() - start_time,
            )

    def _process_pdf(self, path: Path) -> OCRResult:
        """Process a PDF file."""
        start_time = time.time()

        logger.info(f"Processing PDF: {path.name}")

        try:
            # Upload PDF to Mistral
            @retry_with_backoff
            def upload_file():
                with open(path, "rb") as f:
                    return self.client.files.upload(
                        file=File(
                            file_name=path.name,
                            content=f.read(),
                        ),
                        purpose="ocr"
                    )

            uploaded = upload_file()

            # Get signed URL
            @retry_with_backoff
            def get_url():
                return self.client.files.get_signed_url(file_id=uploaded.id)

            signed_url = get_url()

            # Process OCR
            @retry_with_backoff
            def perform_ocr():
                return self.client.ocr.process(
                    model=self.model,
                    document={
                        "document_url": signed_url.url,
                        "type": "document_url"
                    },
                    include_image_base64=False,
                    image_limit=1000,
                    image_min_size=100
                )

            response = perform_ocr()
            processing_time = time.time() - start_time

            pages = []
            for i, page in enumerate(response.pages):
                pages.append(OCRPage(
                    page_number=i + 1,
                    text=page.markdown.replace("\\", ""),
                    markdown=page.markdown,
                    width=page.dimensions.width if page.dimensions else None,
                    height=page.dimensions.height if page.dimensions else None,
                    dpi=page.dimensions.dpi if page.dimensions else None,
                ))

            return OCRResult(
                file_path=str(path),
                file_name=path.name,
                file_type="pdf",
                mime_type="application/pdf",
                pages=pages,
                total_pages=len(pages),
                processing_time=processing_time,
                file_size_kb=path.stat().st_size / 1024,
                model=response.model,
                success=True,
            )

        except Exception as e:
            logger.error(f"PDF OCR failed for {path.name}: {e}")
            return OCRResult(
                file_path=str(path),
                file_name=path.name,
                file_type="pdf",
                mime_type="application/pdf",
                success=False,
                error=str(e),
                processing_time=time.time() - start_time,
            )


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python -m scanner.ocr <file_path>")
        print("Supported formats: PNG, JPEG, WEBP, GIF, PDF")
        sys.exit(1)

    file_path = sys.argv[1]

    try:
        ocr = MistralOCR()
        print(f"Processing: {file_path}")
        result = ocr.process_file(file_path)

        if result.success:
            print(f"\nSuccess! Processed {result.total_pages} page(s) in {result.processing_time:.2f}s")
            print(f"File size: {result.file_size_kb:.2f} KB")
            print(f"Model: {result.model}")
            print("\n" + "=" * 60)
            print("EXTRACTED TEXT:")
            print("=" * 60)
            print(result.full_text)
        else:
            print(f"\nFailed: {result.error}")
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
