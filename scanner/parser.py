#!/usr/bin/env python3
"""
Grade Parser - Extract assignment info and grades from OCR text.

Parses scanned homework, tests, and other school documents to extract:
- Assignment/test name
- Date (due date, test date, etc.)
- Score (points earned / points possible)
- Student name
- Course/subject
"""

import re
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ParsedScore:
    """Extracted score information."""
    earned: float
    possible: float
    percentage: float
    letter_grade: Optional[str] = None
    raw_text: str = ""


@dataclass
class ParsedDocument:
    """Parsed information from a scanned document."""
    # Core extracted data
    title: Optional[str] = None
    date: Optional[datetime] = None
    score: Optional[ParsedScore] = None
    student_name: Optional[str] = None
    course_name: Optional[str] = None

    # Confidence scores (0-100)
    title_confidence: float = 0.0
    date_confidence: float = 0.0
    score_confidence: float = 0.0

    # Raw text for reference
    raw_text: str = ""

    # All potential matches found
    all_titles: List[str] = field(default_factory=list)
    all_dates: List[datetime] = field(default_factory=list)
    all_scores: List[ParsedScore] = field(default_factory=list)


class GradeParser:
    """
    Parser for extracting grade information from OCR text.

    Handles common formats found on school papers:
    - "Score: 85/100"
    - "Grade: B+"
    - "45 out of 50 points"
    - Dates in various formats
    - Assignment titles from headers
    """

    # Score patterns (ordered by specificity)
    SCORE_PATTERNS = [
        # "85/100" or "85 / 100" or "85 out of 100"
        r"(\d+(?:\.\d+)?)\s*(?:/|out of|of)\s*(\d+(?:\.\d+)?)\s*(?:points?|pts?)?",
        # "Score: 85" with possible max
        r"score[:\s]+(\d+(?:\.\d+)?)\s*(?:/\s*(\d+(?:\.\d+)?))?",
        # "Grade: 85%" or "85%"
        r"(?:grade[:\s]+)?(\d+(?:\.\d+)?)\s*%",
        # "Points: 45/50"
        r"points?[:\s]+(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)",
        # Raw fraction at end of line
        r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*$",
    ]

    # Letter grade patterns
    LETTER_GRADE_PATTERNS = [
        r"grade[:\s]*([A-F][+-]?)",
        r"\b([A-F][+-]?)\s*(?:\d+%|\(\d+)",  # "A (95%)" or "B+ 88%"
    ]

    # Date patterns
    DATE_PATTERNS = [
        # MM/DD/YYYY or MM-DD-YYYY
        (r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", "%m/%d/%Y"),
        # MM/DD/YY
        (r"(\d{1,2})[/-](\d{1,2})[/-](\d{2})\b", "%m/%d/%y"),
        # Month DD, YYYY
        (r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", None),
        # Mon DD, YYYY
        (r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", None),
        # YYYY-MM-DD
        (r"(\d{4})-(\d{2})-(\d{2})", "%Y-%m-%d"),
    ]

    # Title patterns (headers, labels)
    TITLE_PATTERNS = [
        r"^(?:name[:\s]*)?(.+?)\s*(?:test|quiz|exam|homework|hw|assignment|worksheet)",
        r"(?:test|quiz|exam|homework|hw|assignment|worksheet)[:\s]*(.+?)$",
        r"^chapter\s+\d+.*",
        r"^unit\s+\d+.*",
        r"^lesson\s+\d+.*",
    ]

    # Common subject/course indicators
    COURSE_PATTERNS = [
        r"(?:class|course|subject)[:\s]*(.+?)(?:\n|$)",
        r"^(math|mathematics|science|reading|english|history|social studies|art|music|pe|spanish|french)\b",
    ]

    # Student name patterns
    NAME_PATTERNS = [
        r"(?:name|student)[:\s]*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*$",
    ]

    def __init__(self):
        """Initialize the parser."""
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for performance."""
        self._score_patterns = [
            re.compile(p, re.IGNORECASE | re.MULTILINE)
            for p in self.SCORE_PATTERNS
        ]
        self._letter_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in self.LETTER_GRADE_PATTERNS
        ]
        self._title_patterns = [
            re.compile(p, re.IGNORECASE | re.MULTILINE)
            for p in self.TITLE_PATTERNS
        ]
        self._course_patterns = [
            re.compile(p, re.IGNORECASE | re.MULTILINE)
            for p in self.COURSE_PATTERNS
        ]
        self._name_patterns = [
            re.compile(p, re.MULTILINE)
            for p in self.NAME_PATTERNS
        ]

    def parse(self, text: str) -> ParsedDocument:
        """
        Parse OCR text to extract assignment information.

        Args:
            text: Raw OCR text from scanned document

        Returns:
            ParsedDocument with extracted information
        """
        result = ParsedDocument(raw_text=text)

        # Extract all components
        result.all_scores = self._extract_scores(text)
        result.all_dates = self._extract_dates(text)
        result.all_titles = self._extract_titles(text)

        # Pick best matches
        if result.all_scores:
            result.score = result.all_scores[0]
            result.score_confidence = self._calculate_score_confidence(result.score, text)

        if result.all_dates:
            result.date = result.all_dates[0]
            result.date_confidence = self._calculate_date_confidence(result.date, text)

        if result.all_titles:
            result.title = result.all_titles[0]
            result.title_confidence = self._calculate_title_confidence(result.title, text)

        # Extract student name and course
        result.student_name = self._extract_student_name(text)
        result.course_name = self._extract_course_name(text)

        return result

    def _extract_scores(self, text: str) -> List[ParsedScore]:
        """Extract all potential scores from text."""
        scores = []

        for pattern in self._score_patterns:
            for match in pattern.finditer(text):
                groups = match.groups()
                try:
                    if len(groups) >= 2 and groups[1]:
                        earned = float(groups[0])
                        possible = float(groups[1])

                        # Skip if this looks like a date (month/day or day/year)
                        if self._looks_like_date(earned, possible, match.group(0)):
                            continue

                        if possible > 0:
                            percentage = (earned / possible) * 100
                            # Skip unrealistic percentages (likely date fragments)
                            if percentage > 200 or possible > 1000:
                                continue
                            scores.append(ParsedScore(
                                earned=earned,
                                possible=possible,
                                percentage=round(percentage, 1),
                                raw_text=match.group(0)
                            ))
                    elif len(groups) >= 1:
                        # Percentage only
                        percentage = float(groups[0])
                        if 0 <= percentage <= 100:
                            scores.append(ParsedScore(
                                earned=percentage,
                                possible=100,
                                percentage=percentage,
                                raw_text=match.group(0)
                            ))
                except (ValueError, ZeroDivisionError):
                    continue

        # Extract letter grades
        for pattern in self._letter_patterns:
            for match in pattern.finditer(text):
                letter = match.group(1).upper()
                # Update scores with letter grade if found
                for score in scores:
                    if not score.letter_grade:
                        score.letter_grade = letter
                        break
                else:
                    # Add letter grade only score
                    scores.append(ParsedScore(
                        earned=0,
                        possible=0,
                        percentage=self._letter_to_percentage(letter),
                        letter_grade=letter,
                        raw_text=match.group(0)
                    ))

        # Sort by confidence (scores with both earned/possible first)
        scores.sort(key=lambda s: (s.possible > 0, s.earned > 0), reverse=True)

        return scores

    def _letter_to_percentage(self, letter: str) -> float:
        """Convert letter grade to approximate percentage."""
        grades = {
            "A+": 97, "A": 94, "A-": 90,
            "B+": 87, "B": 84, "B-": 80,
            "C+": 77, "C": 74, "C-": 70,
            "D+": 67, "D": 64, "D-": 60,
            "F": 50,
        }
        return grades.get(letter.upper(), 0)

    def _looks_like_date(self, num1: float, num2: float, raw_text: str) -> bool:
        """Check if two numbers look like they're part of a date."""
        # Check for month/day pattern (1-12 / 1-31)
        if 1 <= num1 <= 12 and 1 <= num2 <= 31:
            return True

        # Check for day/year pattern (1-31 / 2020-2030)
        if 1 <= num1 <= 31 and 2020 <= num2 <= 2030:
            return True

        # Check if the raw text has date-like context
        date_context = re.search(r"date|due|\d{4}", raw_text, re.I)
        if date_context and (1 <= num1 <= 31 or 1 <= num2 <= 31):
            return True

        return False

    def _extract_dates(self, text: str) -> List[datetime]:
        """Extract all potential dates from text."""
        dates = []
        current_year = datetime.now().year

        for pattern_str, fmt in self.DATE_PATTERNS:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            for match in pattern.finditer(text):
                try:
                    if fmt:
                        # Reconstruct date string for parsing
                        date_str = "/".join(match.groups())
                        date = datetime.strptime(date_str, fmt.replace("/", "/"))
                    else:
                        # Handle month name formats
                        groups = match.groups()
                        month_str = groups[0]
                        day = int(groups[1])
                        year = int(groups[2])

                        # Parse month name
                        month_names = {
                            "january": 1, "jan": 1,
                            "february": 2, "feb": 2,
                            "march": 3, "mar": 3,
                            "april": 4, "apr": 4,
                            "may": 5,
                            "june": 6, "jun": 6,
                            "july": 7, "jul": 7,
                            "august": 8, "aug": 8,
                            "september": 9, "sep": 9,
                            "october": 10, "oct": 10,
                            "november": 11, "nov": 11,
                            "december": 12, "dec": 12,
                        }
                        month = month_names.get(month_str.lower(), 1)
                        date = datetime(year, month, day)

                    # Sanity check: date should be within reasonable range
                    if current_year - 2 <= date.year <= current_year + 1:
                        dates.append(date)

                except (ValueError, KeyError):
                    continue

        # Sort by proximity to current date
        now = datetime.now()
        dates.sort(key=lambda d: abs((d - now).days))

        return dates

    def _extract_titles(self, text: str) -> List[str]:
        """Extract potential assignment/test titles."""
        titles = []
        lines = text.split("\n")

        for pattern in self._title_patterns:
            for match in pattern.finditer(text):
                title = match.group(0).strip()
                if title and len(title) > 3:
                    titles.append(self._clean_title(title))

        # Also check first few non-empty lines as potential titles
        for line in lines[:5]:
            line = line.strip()
            if line and len(line) > 5 and len(line) < 100:
                # Skip lines that look like scores or dates
                if not re.search(r"^\d+[/-]|^score|^grade|^name|^date", line, re.I):
                    titles.append(self._clean_title(line))

        # Remove duplicates while preserving order
        seen = set()
        unique_titles = []
        for t in titles:
            t_lower = t.lower()
            if t_lower not in seen:
                seen.add(t_lower)
                unique_titles.append(t)

        return unique_titles

    def _clean_title(self, title: str) -> str:
        """Clean up extracted title."""
        # Remove common prefixes/suffixes
        title = re.sub(r"^(name[:\s]*|date[:\s]*)", "", title, flags=re.I)
        title = re.sub(r"\s*[-_]\s*$", "", title)
        return title.strip()

    def _extract_student_name(self, text: str) -> Optional[str]:
        """Extract student name from text."""
        for pattern in self._name_patterns:
            match = pattern.search(text)
            if match:
                name = match.group(1).strip()
                if len(name.split()) >= 2:  # At least first and last name
                    return name
        return None

    def _extract_course_name(self, text: str) -> Optional[str]:
        """Extract course/subject name from text."""
        for pattern in self._course_patterns:
            match = pattern.search(text)
            if match:
                return match.group(1).strip() if match.lastindex else match.group(0).strip()
        return None

    def _calculate_score_confidence(self, score: ParsedScore, text: str) -> float:
        """Calculate confidence in extracted score."""
        confidence = 50.0

        # Higher confidence if both earned and possible are present
        if score.possible > 0:
            confidence += 20

        # Higher confidence if score appears near keywords
        score_context = re.search(
            rf"(?:score|grade|points?)[:\s]*{re.escape(score.raw_text)}",
            text, re.I
        )
        if score_context:
            confidence += 20

        # Letter grade increases confidence
        if score.letter_grade:
            confidence += 10

        return min(confidence, 100)

    def _calculate_date_confidence(self, date: datetime, text: str) -> float:
        """Calculate confidence in extracted date."""
        confidence = 50.0

        # Higher confidence if date appears near keywords
        date_keywords = ["date", "due", "test", "quiz", "submitted"]
        for keyword in date_keywords:
            if re.search(rf"{keyword}[:\s]*.*{date.month}[/-]{date.day}", text, re.I):
                confidence += 15
                break

        # Recent dates are more likely correct
        days_diff = abs((datetime.now() - date).days)
        if days_diff < 30:
            confidence += 20
        elif days_diff < 90:
            confidence += 10

        return min(confidence, 100)

    def _calculate_title_confidence(self, title: str, text: str) -> float:
        """Calculate confidence in extracted title."""
        confidence = 40.0

        # Keywords increase confidence
        keywords = ["test", "quiz", "exam", "homework", "assignment", "chapter", "unit"]
        for keyword in keywords:
            if keyword in title.lower():
                confidence += 15
                break

        # Title appearing at start of document
        if text.strip().lower().startswith(title.lower()[:20]):
            confidence += 20

        # Longer titles that aren't too long
        if 10 < len(title) < 50:
            confidence += 10

        return min(confidence, 100)


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    # Test with sample text
    sample_text = """
    Name: John Smith
    Date: 01/15/2024

    Math 3 - Chapter 5 Test
    Fractions and Decimals

    Score: 42/50
    Grade: B+

    Good work on problem solving!
    """

    parser = GradeParser()
    result = parser.parse(sample_text)

    print("Parsed Document:")
    print(f"  Title: {result.title} (confidence: {result.title_confidence:.0f}%)")
    print(f"  Date: {result.date} (confidence: {result.date_confidence:.0f}%)")
    if result.score:
        print(f"  Score: {result.score.earned}/{result.score.possible} = {result.score.percentage}%")
        print(f"  Letter: {result.score.letter_grade}")
        print(f"  (confidence: {result.score_confidence:.0f}%)")
    print(f"  Student: {result.student_name}")
    print(f"  Course: {result.course_name}")
