#!/usr/bin/env python3
"""
Student Detector - Smart identification of which student a document belongs to.

Uses multiple signals to determine document ownership:
1. QR Code (future) - 100% confidence
2. OCR Name Match - 95% confidence for exact, 70% for partial
3. Course Detection - 85% for unique course, 50% for shared
4. Assignment Context - 75% for strong title match
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from database.models import Student, Course, Assignment
from .parser import ParsedDocument

logger = logging.getLogger(__name__)


@dataclass
class StudentDetection:
    """Result of student detection attempt."""
    student: Optional[Student]
    confidence: float  # 0-100
    method: str  # "qr_code", "ocr_name", "course_match", "assignment_match", "ambiguous"
    reasons: List[str] = field(default_factory=list)

    @property
    def is_confident(self) -> bool:
        """Check if detection is confident enough for auto-assignment."""
        return self.confidence >= 70 and self.student is not None


class StudentDetector:
    """
    Detects which student a scanned document belongs to.

    Uses a hierarchy of detection methods, returning the first
    confident match found.
    """

    # Confidence thresholds
    QR_CODE_CONFIDENCE = 100
    COVER_SHEET_CONFIDENCE = 98  # Cover sheet with clear name
    EXACT_NAME_CONFIDENCE = 95
    PARTIAL_NAME_CONFIDENCE = 70
    UNIQUE_COURSE_CONFIDENCE = 85
    SHARED_COURSE_CONFIDENCE = 50
    ASSIGNMENT_MATCH_CONFIDENCE = 75
    TITLE_SIMILARITY_THRESHOLD = 0.7

    def __init__(self, session: Session):
        """
        Initialize detector with database session.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self._students = None
        self._courses_by_student = None

    @property
    def students(self) -> List[Student]:
        """Get all students (cached)."""
        if self._students is None:
            self._students = self.session.query(Student).all()
        return self._students

    def _get_courses_by_student(self) -> dict:
        """Get courses grouped by student ID (cached)."""
        if self._courses_by_student is None:
            self._courses_by_student = {}
            courses = self.session.query(Course).filter_by(is_active=True).all()
            for course in courses:
                if course.student_id not in self._courses_by_student:
                    self._courses_by_student[course.student_id] = []
                self._courses_by_student[course.student_id].append(course)
        return self._courses_by_student

    def detect(self, parsed: ParsedDocument, qr_data: dict = None, raw_text: str = None) -> StudentDetection:
        """
        Detect which student a document belongs to.

        Args:
            parsed: Parsed document information from OCR
            qr_data: Optional QR code data if detected
            raw_text: Optional raw OCR text for cover sheet detection

        Returns:
            StudentDetection with student, confidence, and reasoning
        """
        reasons = []

        # 1. Try QR code (highest confidence)
        if qr_data:
            result = self._detect_from_qr(qr_data)
            if result.student:
                return result

        # 2. Try cover sheet detection (check first part of text for clean name)
        text_to_check = raw_text or parsed.raw_text
        if text_to_check:
            result = self._detect_from_cover_sheet(text_to_check)
            if result.is_confident:
                return result
            reasons.extend(result.reasons)

        # 3. Try OCR name match
        if parsed.student_name:
            result = self._detect_from_name(parsed.student_name)
            if result.is_confident:
                return result
            reasons.extend(result.reasons)

        # 4. Try course detection
        if parsed.course_name:
            result = self._detect_from_course(parsed.course_name)
            if result.is_confident:
                return result
            reasons.extend(result.reasons)

        # 5. Try assignment title match
        if parsed.title:
            result = self._detect_from_assignment(parsed.title, parsed.date)
            if result.is_confident:
                return result
            reasons.extend(result.reasons)

        # 6. Ambiguous - couldn't determine student
        if not reasons:
            reasons = ["No identifying information found in document"]

        return StudentDetection(
            student=None,
            confidence=0,
            method="ambiguous",
            reasons=reasons
        )

    def _detect_from_qr(self, qr_data: dict) -> StudentDetection:
        """Detect student from QR code data."""
        student_id = qr_data.get("student_id")
        if student_id:
            student = self.session.query(Student).filter_by(id=student_id).first()
            if student:
                return StudentDetection(
                    student=student,
                    confidence=self.QR_CODE_CONFIDENCE,
                    method="qr_code",
                    reasons=[f"QR code identified student: {student.name}"]
                )
        return StudentDetection(
            student=None,
            confidence=0,
            method="qr_code",
            reasons=["QR code present but invalid student ID"]
        )

    def _detect_from_cover_sheet(self, text: str) -> StudentDetection:
        """
        Detect student from cover sheet.

        Looks for student name in both the first AND last portions of the OCR text.
        Cover sheet may be at the end if scanner feeds from bottom of stack.

        Args:
            text: Full OCR text from document

        Returns:
            StudentDetection with high confidence if cover sheet found
        """
        import re

        # Check both beginning and end of document
        # Cover sheet at start: first 500 chars
        # Cover sheet at end: last 500 chars (scanner feeds from bottom)
        first_part = text[:500].upper()
        last_part = text[-500:].upper() if len(text) > 500 else ""

        def clean_text(t: str) -> str:
            """Remove OCR artifacts and normalize whitespace."""
            cleaned = re.sub(r'[^\w\s]', ' ', t)
            return ' '.join(cleaned.split())

        first_part_clean = clean_text(first_part)
        last_part_clean = clean_text(last_part)

        best_match = None
        best_position = float('inf')
        found_at_end = False

        for student in self.students:
            # Get variations of student name to check
            name_upper = student.name.upper()
            first_name = name_upper.split()[0]

            # Check FIRST part of document
            for name_variant in [first_name, name_upper]:
                if name_variant in first_part_clean:
                    pos = first_part_clean.find(name_variant)
                    if pos < best_position:
                        best_match = student
                        best_position = pos
                        found_at_end = False

            # Check LAST part of document (cover sheet at end due to scanner feed)
            if last_part_clean:
                for name_variant in [first_name, name_upper]:
                    if name_variant in last_part_clean:
                        pos = last_part_clean.find(name_variant)
                        # For end of document, treat early position as high confidence
                        if pos < 200 and (best_position > 200 or found_at_end):
                            best_match = student
                            best_position = pos
                            found_at_end = True
                        elif pos < best_position and best_position > 200:
                            best_match = student
                            best_position = pos
                            found_at_end = True

        if best_match and best_position < 200:
            # Found name near start of section - high confidence cover sheet
            location = "end" if found_at_end else "beginning"
            return StudentDetection(
                student=best_match,
                confidence=self.COVER_SHEET_CONFIDENCE,
                method="cover_sheet",
                reasons=[f"Cover sheet detected at {location}: '{best_match.name}' found at position {best_position}"]
            )
        elif best_match:
            # Found name but not prominently - moderate confidence
            location = "end" if found_at_end else "beginning"
            return StudentDetection(
                student=best_match,
                confidence=self.PARTIAL_NAME_CONFIDENCE,
                method="cover_sheet",
                reasons=[f"Name '{best_match.name}' found at {location} of document (position {best_position})"]
            )

        return StudentDetection(
            student=None,
            confidence=0,
            method="cover_sheet",
            reasons=["No student name found in first or last portion of document"]
        )

    def _detect_from_name(self, name: str) -> StudentDetection:
        """Detect student from OCR-extracted name."""
        name_lower = name.lower().strip()
        name_parts = name_lower.split()

        best_match = None
        best_confidence = 0
        reasons = []

        for student in self.students:
            student_name_lower = student.name.lower()
            student_parts = student_name_lower.split()

            # Exact match
            if name_lower == student_name_lower:
                return StudentDetection(
                    student=student,
                    confidence=self.EXACT_NAME_CONFIDENCE,
                    method="ocr_name",
                    reasons=[f"Exact name match: '{name}' = '{student.name}'"]
                )

            # First name match
            if name_parts and student_parts:
                if name_parts[0] == student_parts[0]:
                    if self.PARTIAL_NAME_CONFIDENCE > best_confidence:
                        best_match = student
                        best_confidence = self.PARTIAL_NAME_CONFIDENCE
                        reasons = [f"First name match: '{name_parts[0]}' in '{student.name}'"]

            # Last name match (if we have both parts)
            if len(name_parts) >= 2 and len(student_parts) >= 2:
                if name_parts[-1] == student_parts[-1]:
                    if self.PARTIAL_NAME_CONFIDENCE > best_confidence:
                        best_match = student
                        best_confidence = self.PARTIAL_NAME_CONFIDENCE
                        reasons = [f"Last name match: '{name_parts[-1]}' in '{student.name}'"]

            # Fuzzy match
            similarity = SequenceMatcher(None, name_lower, student_name_lower).ratio()
            if similarity > 0.8:
                fuzzy_confidence = int(similarity * 100)
                if fuzzy_confidence > best_confidence:
                    best_match = student
                    best_confidence = fuzzy_confidence
                    reasons = [f"Fuzzy name match: '{name}' ~ '{student.name}' ({fuzzy_confidence}%)"]

        if best_match and best_confidence >= self.PARTIAL_NAME_CONFIDENCE:
            return StudentDetection(
                student=best_match,
                confidence=best_confidence,
                method="ocr_name",
                reasons=reasons
            )

        return StudentDetection(
            student=None,
            confidence=best_confidence,
            method="ocr_name",
            reasons=reasons if reasons else [f"No student match for name: '{name}'"]
        )

    def _detect_from_course(self, course_name: str) -> StudentDetection:
        """Detect student from course name."""
        course_lower = course_name.lower().strip()
        courses_by_student = self._get_courses_by_student()

        matching_students = []
        reasons = []

        for student in self.students:
            student_courses = courses_by_student.get(student.id, [])
            for course in student_courses:
                course_name_lower = course.name.lower()

                # Check for course name match
                if course_lower in course_name_lower or course_name_lower in course_lower:
                    matching_students.append((student, course))
                    break

                # Fuzzy match on course name
                similarity = SequenceMatcher(None, course_lower, course_name_lower).ratio()
                if similarity > 0.7:
                    matching_students.append((student, course))
                    break

        if len(matching_students) == 1:
            student, course = matching_students[0]
            return StudentDetection(
                student=student,
                confidence=self.UNIQUE_COURSE_CONFIDENCE,
                method="course_match",
                reasons=[f"Unique course match: '{course_name}' → {student.name}'s '{course.name}'"]
            )
        elif len(matching_students) > 1:
            student_names = [s.name for s, _ in matching_students]
            return StudentDetection(
                student=None,
                confidence=self.SHARED_COURSE_CONFIDENCE,
                method="course_match",
                reasons=[f"Course '{course_name}' shared by: {', '.join(student_names)}"]
            )

        return StudentDetection(
            student=None,
            confidence=0,
            method="course_match",
            reasons=[f"No course match for: '{course_name}'"]
        )

    def _detect_from_assignment(self, title: str, date=None) -> StudentDetection:
        """Detect student from assignment title match."""
        title_lower = title.lower().strip()

        # Query recent assignments
        query = self.session.query(Assignment).join(Course).filter(
            Course.is_active == True
        )

        # If we have a date, narrow the search
        if date:
            from datetime import timedelta
            query = query.filter(
                Assignment.due_at.between(
                    date - timedelta(days=14),
                    date + timedelta(days=14)
                )
            )
        else:
            # Look at recent assignments only
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(days=60)
            query = query.filter(Assignment.due_at >= cutoff)

        assignments = query.all()

        best_match = None
        best_similarity = 0
        best_assignment = None

        for assignment in assignments:
            assignment_title_lower = assignment.name.lower()
            similarity = SequenceMatcher(None, title_lower, assignment_title_lower).ratio()

            if similarity > best_similarity:
                best_similarity = similarity
                best_assignment = assignment
                # Get student from course
                course = self.session.query(Course).filter_by(id=assignment.course_id).first()
                if course:
                    best_match = self.session.query(Student).filter_by(id=course.student_id).first()

        if best_match and best_similarity >= self.TITLE_SIMILARITY_THRESHOLD:
            confidence = int(best_similarity * self.ASSIGNMENT_MATCH_CONFIDENCE)
            return StudentDetection(
                student=best_match,
                confidence=confidence,
                method="assignment_match",
                reasons=[
                    f"Assignment title match: '{title}' ~ '{best_assignment.name}' ({int(best_similarity*100)}%)",
                    f"Belongs to {best_match.name}"
                ]
            )

        return StudentDetection(
            student=None,
            confidence=0,
            method="assignment_match",
            reasons=[f"No assignment match for title: '{title}'"]
        )


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    print("Student Detector Test")
    print("=" * 50)

    from database.connection import get_session

    session = get_session()
    detector = StudentDetector(session)

    # Show available students
    print("\nAvailable students:")
    for student in detector.students:
        print(f"  - {student.name} (ID: {student.id})")

    # Test with sample parsed document
    from .parser import ParsedDocument

    test_doc = ParsedDocument(
        title="Chapter 5 Math Quiz",
        student_name="JJ",
        course_name="Math",
    )

    print(f"\nTest document:")
    print(f"  Title: {test_doc.title}")
    print(f"  Student name: {test_doc.student_name}")
    print(f"  Course: {test_doc.course_name}")

    result = detector.detect(test_doc)
    print(f"\nDetection result:")
    print(f"  Student: {result.student.name if result.student else 'Unknown'}")
    print(f"  Confidence: {result.confidence}%")
    print(f"  Method: {result.method}")
    print(f"  Reasons: {result.reasons}")
