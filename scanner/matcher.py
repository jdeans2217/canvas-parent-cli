#!/usr/bin/env python3
"""
Assignment Matcher - Match scanned documents to Canvas assignments.

Uses fuzzy matching on title, date proximity, and course name to find
the best matching Canvas assignment for a scanned document.
"""

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, List, Tuple
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from database.models import Assignment, Course, Student
from .parser import ParsedDocument

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Result of matching a scanned document to a Canvas assignment."""
    assignment: Optional[Assignment]
    confidence: float  # 0-100
    method: str  # "title", "date", "title+date", "manual"
    reasons: List[str]

    @property
    def is_confident_match(self) -> bool:
        """Check if match confidence is high enough for auto-assignment."""
        return self.confidence >= 70


class AssignmentMatcher:
    """
    Matches scanned documents to Canvas assignments.

    Uses multiple matching strategies:
    1. Title similarity (fuzzy matching)
    2. Date proximity (within N days of due date)
    3. Course name matching
    4. Combined scoring
    """

    def __init__(
        self,
        session: Session,
        title_weight: float = 0.5,
        date_weight: float = 0.3,
        course_weight: float = 0.2,
        date_tolerance_days: int = 7,
    ):
        """
        Initialize the matcher.

        Args:
            session: SQLAlchemy database session
            title_weight: Weight for title similarity (0-1)
            date_weight: Weight for date proximity (0-1)
            course_weight: Weight for course name match (0-1)
            date_tolerance_days: Max days difference for date matching
        """
        self.session = session
        self.title_weight = title_weight
        self.date_weight = date_weight
        self.course_weight = course_weight
        self.date_tolerance_days = date_tolerance_days

    def find_match(
        self,
        parsed: ParsedDocument,
        student_id: int,
        course_id: Optional[int] = None,
    ) -> MatchResult:
        """
        Find the best matching assignment for a parsed document.

        Args:
            parsed: Parsed document information
            student_id: Student's database ID
            course_id: Optional course ID to narrow search

        Returns:
            MatchResult with best match and confidence
        """
        # Get candidate assignments
        candidates = self._get_candidates(student_id, course_id, parsed.date)

        if not candidates:
            return MatchResult(
                assignment=None,
                confidence=0,
                method="none",
                reasons=["No candidate assignments found"]
            )

        # Score each candidate
        scored = []
        for assignment in candidates:
            score, reasons = self._score_match(parsed, assignment)
            scored.append((assignment, score, reasons))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        best_assignment, best_score, best_reasons = scored[0]

        # Determine match method
        method = self._determine_method(best_reasons)

        return MatchResult(
            assignment=best_assignment,
            confidence=best_score,
            method=method,
            reasons=best_reasons
        )

    def find_matches(
        self,
        parsed: ParsedDocument,
        student_id: int,
        course_id: Optional[int] = None,
        limit: int = 5,
    ) -> List[MatchResult]:
        """
        Find multiple potential matches ranked by confidence.

        Args:
            parsed: Parsed document information
            student_id: Student's database ID
            course_id: Optional course ID to narrow search
            limit: Maximum number of matches to return

        Returns:
            List of MatchResults sorted by confidence
        """
        candidates = self._get_candidates(student_id, course_id, parsed.date)

        results = []
        for assignment in candidates:
            score, reasons = self._score_match(parsed, assignment)
            method = self._determine_method(reasons)
            results.append(MatchResult(
                assignment=assignment,
                confidence=score,
                method=method,
                reasons=reasons
            ))

        # Sort by confidence and limit
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[:limit]

    def _get_candidates(
        self,
        student_id: int,
        course_id: Optional[int],
        date: Optional[datetime],
    ) -> List[Assignment]:
        """Get candidate assignments for matching."""
        # Start with base query
        query = (
            self.session.query(Assignment)
            .join(Course)
            .filter(Course.student_id == student_id)
        )

        # Filter by course if specified
        if course_id:
            query = query.filter(Course.id == course_id)

        # Filter by date range if available
        if date:
            start_date = date - timedelta(days=self.date_tolerance_days * 2)
            end_date = date + timedelta(days=self.date_tolerance_days * 2)
            query = query.filter(
                Assignment.due_at.between(start_date, end_date)
            )
        else:
            # If no date, look at recent assignments (last 30 days)
            cutoff = datetime.now() - timedelta(days=30)
            query = query.filter(Assignment.due_at >= cutoff)

        return query.all()

    def _score_match(
        self,
        parsed: ParsedDocument,
        assignment: Assignment,
    ) -> Tuple[float, List[str]]:
        """
        Calculate match score between parsed document and assignment.

        Returns:
            Tuple of (score 0-100, list of reasons)
        """
        reasons = []
        scores = {
            "title": 0.0,
            "date": 0.0,
            "course": 0.0,
        }

        # Title similarity
        if parsed.title:
            title_sim = self._string_similarity(
                parsed.title.lower(),
                assignment.name.lower()
            )
            scores["title"] = title_sim * 100

            if title_sim > 0.8:
                reasons.append(f"Title match: {title_sim:.0%} similar")
            elif title_sim > 0.5:
                reasons.append(f"Partial title match: {title_sim:.0%} similar")

        # Date proximity
        if parsed.date and assignment.due_at:
            days_diff = abs((parsed.date - assignment.due_at).days)

            if days_diff == 0:
                scores["date"] = 100
                reasons.append("Exact date match")
            elif days_diff <= self.date_tolerance_days:
                # Linear decay within tolerance
                scores["date"] = 100 * (1 - days_diff / (self.date_tolerance_days + 1))
                reasons.append(f"Date within {days_diff} days")

        # Course name match
        if parsed.course_name and assignment.course:
            course_sim = self._string_similarity(
                parsed.course_name.lower(),
                assignment.course.name.lower()
            )
            scores["course"] = course_sim * 100

            if course_sim > 0.7:
                reasons.append(f"Course name match: {assignment.course.name}")

        # Calculate weighted total
        total = (
            scores["title"] * self.title_weight +
            scores["date"] * self.date_weight +
            scores["course"] * self.course_weight
        )

        # Bonus for multiple strong signals
        strong_signals = sum(1 for s in scores.values() if s > 70)
        if strong_signals >= 2:
            total = min(total + 10, 100)
            reasons.append("Multiple strong matches")

        return total, reasons

    def _string_similarity(self, a: str, b: str) -> float:
        """
        Calculate similarity between two strings using SequenceMatcher.

        Returns:
            Similarity ratio (0-1)
        """
        return SequenceMatcher(None, a, b).ratio()

    def _determine_method(self, reasons: List[str]) -> str:
        """Determine the primary matching method from reasons."""
        has_title = any("title" in r.lower() for r in reasons)
        has_date = any("date" in r.lower() for r in reasons)

        if has_title and has_date:
            return "title+date"
        elif has_title:
            return "title"
        elif has_date:
            return "date"
        else:
            return "auto"


def match_document_to_assignment(
    session: Session,
    parsed: ParsedDocument,
    student_id: int,
    course_id: Optional[int] = None,
) -> MatchResult:
    """
    Convenience function to match a document to an assignment.

    Args:
        session: Database session
        parsed: Parsed document info
        student_id: Student's database ID
        course_id: Optional course ID

    Returns:
        MatchResult with best match
    """
    matcher = AssignmentMatcher(session)
    return matcher.find_match(parsed, student_id, course_id)


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    from database.connection import get_session

    print("Assignment Matcher Test")
    print("=" * 50)

    # Create test parsed document
    parsed = ParsedDocument(
        title="Chapter 5 Math Test - Fractions",
        date=datetime(2024, 1, 15),
        course_name="Math 3",
    )

    print(f"Looking for match:")
    print(f"  Title: {parsed.title}")
    print(f"  Date: {parsed.date}")
    print(f"  Course: {parsed.course_name}")

    try:
        session = get_session()

        # Get first student
        student = session.query(Student).first()
        if student:
            matcher = AssignmentMatcher(session)
            result = matcher.find_match(parsed, student.id)

            print(f"\nBest Match:")
            if result.assignment:
                print(f"  Assignment: {result.assignment.name}")
                print(f"  Course: {result.assignment.course.name}")
                print(f"  Due: {result.assignment.due_at}")
            print(f"  Confidence: {result.confidence:.1f}%")
            print(f"  Method: {result.method}")
            print(f"  Reasons: {', '.join(result.reasons)}")
        else:
            print("No students in database")

    except Exception as e:
        print(f"Error: {e}")
