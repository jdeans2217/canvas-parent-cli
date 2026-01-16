#!/usr/bin/env python3
"""
Scanner Module - Document scanning and OCR for homework processing.

Components:
- ocr: Mistral OCR integration for text extraction
- parser: Extract grades, dates, and assignment info from OCR text
- matcher: Match scanned documents to Canvas assignments
- email_processor: Process email attachments from Gmail
- drive_processor: Process scanned documents from Google Drive
"""

from .ocr import MistralOCR, OCRResult
from .parser import GradeParser, ParsedDocument
from .matcher import AssignmentMatcher, MatchResult
from .email_processor import EmailProcessor, ProcessingResult
from .drive_processor import DriveProcessor, DriveProcessingResult
from .student_detector import StudentDetector, StudentDetection

__all__ = [
    "MistralOCR",
    "OCRResult",
    "GradeParser",
    "ParsedDocument",
    "AssignmentMatcher",
    "MatchResult",
    "EmailProcessor",
    "ProcessingResult",
    "DriveProcessor",
    "DriveProcessingResult",
    "StudentDetector",
    "StudentDetection",
]
