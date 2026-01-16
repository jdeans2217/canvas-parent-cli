#!/usr/bin/env python3
"""
Debrief Collector - Aggregate data for daily debrief reports.

Collects agenda content, grades, assignments, and announcements
for "what happened today" and "what's coming tomorrow" view.
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import canvas_api
from .agenda_parser import AgendaParser, DayAgenda, WeeklyAgenda


@dataclass
class CourseAgenda:
    """Agenda content for a single course."""
    course_id: int
    course_name: str
    yesterday: Optional[DayAgenda] = None  # For "homework due today"
    today: Optional[DayAgenda] = None
    tomorrow: Optional[DayAgenda] = None
    week_agendas: Dict[str, DayAgenda] = field(default_factory=dict)  # Full week for test scanning


@dataclass
class DebriefData:
    """All data for a daily debrief report."""
    student_name: str
    student_id: int
    report_date: date
    day_of_week: str  # "Monday", "Tuesday", etc.
    tomorrow_day: str  # Next school day name

    # Today's data
    course_agendas: List[CourseAgenda] = field(default_factory=list)
    grades_posted_today: List[Dict[str, Any]] = field(default_factory=list)
    announcements_today: List[Dict[str, Any]] = field(default_factory=list)
    assignments_due_today: List[Dict[str, Any]] = field(default_factory=list)

    # Tomorrow's data
    assignments_due_tomorrow: List[Dict[str, Any]] = field(default_factory=list)

    # Context
    missing_assignments: List[Dict[str, Any]] = field(default_factory=list)
    current_grades: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    generated_at: str = ""

    @property
    def today_agendas(self) -> Dict[str, DayAgenda]:
        """Get today's agendas as course_name -> DayAgenda dict (only courses with content)."""
        return {
            ca.course_name: ca.today
            for ca in self.course_agendas
            if ca.today and ca.today.has_content()
        }

    @property
    def tomorrow_agendas(self) -> Dict[str, DayAgenda]:
        """Get tomorrow's agendas as course_name -> DayAgenda dict (only courses with content)."""
        return {
            ca.course_name: ca.tomorrow
            for ca in self.course_agendas
            if ca.tomorrow and ca.tomorrow.has_content()
        }

    @property
    def all_courses_today(self) -> Dict[str, Optional[DayAgenda]]:
        """Get ALL courses with today's agenda (None if no agenda)."""
        return {
            ca.course_name: ca.today
            for ca in self.course_agendas
        }

    @property
    def all_courses_tomorrow(self) -> Dict[str, Optional[DayAgenda]]:
        """Get ALL courses with tomorrow's agenda (None if no agenda)."""
        return {
            ca.course_name: ca.tomorrow
            for ca in self.course_agendas
        }

    def has_today_content(self) -> bool:
        """Check if there's any content for today."""
        return bool(
            self.today_agendas
            or self.grades_posted_today
            or self.announcements_today
            or self.assignments_due_today
        )

    def has_tomorrow_content(self) -> bool:
        """Check if there's any content for tomorrow."""
        return bool(self.tomorrow_agendas or self.assignments_due_tomorrow)

    @property
    def homework_due_today(self) -> Dict[str, List[str]]:
        """Get yesterday's homework that's due today (course_name -> homework items)."""
        result = {}
        for ca in self.course_agendas:
            if ca.yesterday and ca.yesterday.at_home:
                short_name = ca.course_name.split(" - ")[0]
                result[short_name] = ca.yesterday.at_home
        return result

    @staticmethod
    def _is_test_item(text: str) -> bool:
        """Check if text contains a test/quiz keyword as a whole word."""
        import re
        # Use word boundaries to avoid false positives like "greatest" matching "test"
        patterns = [
            r'\btest\b',
            r'\bquiz\b',
            r'\bexam\b',
            r'\bassessment\b',
        ]
        text_lower = text.lower()
        return any(re.search(pattern, text_lower) for pattern in patterns)

    @property
    def tests_today(self) -> List[Dict[str, str]]:
        """Get tests/quizzes happening today."""
        tests = []
        seen = set()
        for ca in self.course_agendas:
            if ca.today:
                for item in (ca.today.in_class or []) + (ca.today.learning_objectives or []):
                    if self._is_test_item(item):
                        key = (ca.course_name, item)
                        if key not in seen:
                            seen.add(key)
                            tests.append({
                                "course": ca.course_name.split(" - ")[0],
                                "description": item
                            })
        return tests

    @property
    def tests_tomorrow(self) -> List[Dict[str, str]]:
        """Get tests/quizzes happening tomorrow (study tonight!)."""
        tests = []
        seen = set()
        for ca in self.course_agendas:
            if ca.tomorrow:
                for item in (ca.tomorrow.in_class or []) + (ca.tomorrow.learning_objectives or []):
                    if self._is_test_item(item):
                        key = (ca.course_name, item)
                        if key not in seen:
                            seen.add(key)
                            tests.append({
                                "course": ca.course_name.split(" - ")[0],
                                "description": item
                            })
        return tests

    @property
    def next_test(self) -> Optional[Dict[str, str]]:
        """Get the next upcoming test (any day, any week)."""
        days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

        try:
            today_idx = days_order.index(self.day_of_week)
        except ValueError:
            return None

        # Check remaining days this week first
        for day_offset in range(1, 5):  # Tomorrow through end of week
            check_idx = today_idx + day_offset
            if check_idx >= len(days_order):
                break
            check_day = days_order[check_idx]

            for ca in self.course_agendas:
                agenda = ca.week_agendas.get(check_day)
                if agenda:
                    for item in (agenda.in_class or []) + (agenda.learning_objectives or []):
                        if self._is_test_item(item):
                            return {
                                "course": ca.course_name.split(" - ")[0],
                                "day": check_day,
                                "description": item
                            }

        # TODO: Could extend to check next week's agenda pages
        return None


class DebriefCollector:
    """Collect and aggregate data for daily debrief."""

    # Page title patterns for weekly agendas (e.g., Q1W1, Q2W3)
    AGENDA_PAGE_PATTERN = re.compile(r"^Q\d+W\d+$", re.IGNORECASE)

    def __init__(self, student_id: int, student_name: str):
        self.student_id = student_id
        self.student_name = student_name
        self.agenda_parser = AgendaParser()
        self._courses_cache: Optional[List[Dict]] = None

    def collect(self, target_date: Optional[date] = None) -> DebriefData:
        """
        Collect all debrief data for the target date.

        Args:
            target_date: Date to generate debrief for (defaults to today)

        Returns:
            DebriefData with all aggregated information
        """
        if target_date is None:
            target_date = date.today()

        # Determine day names, handling weekends
        day_of_week, tomorrow_day, effective_today, effective_tomorrow = (
            self._get_school_days(target_date)
        )

        debrief = DebriefData(
            student_name=self.student_name,
            student_id=self.student_id,
            report_date=target_date,
            day_of_week=day_of_week,
            tomorrow_day=tomorrow_day,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )

        # Get courses
        courses = self._get_courses()

        # Collect agenda content for each course (include ALL courses)
        for course in courses:
            course_agenda = self._collect_course_agenda(
                course, effective_today, effective_tomorrow
            )
            # Always add course, even without agenda
            if course_agenda:
                debrief.course_agendas.append(course_agenda)
            else:
                # Add course with no agenda content
                debrief.course_agendas.append(CourseAgenda(
                    course_id=course["id"],
                    course_name=course.get("name", "Unknown Course"),
                    yesterday=None,
                    today=None,
                    tomorrow=None,
                    week_agendas={},
                ))

        # Collect grades posted today (last 24 hours)
        debrief.grades_posted_today = self._get_grades_posted_today()

        # Collect announcements from today
        debrief.announcements_today = self._get_announcements_today(courses)

        # Collect assignments due today and tomorrow
        upcoming = canvas_api.get_upcoming_assignments(self.student_id, days=2)
        debrief.assignments_due_today = self._filter_by_due_date(upcoming, target_date)
        debrief.assignments_due_tomorrow = self._filter_by_due_date(
            upcoming, effective_tomorrow
        )

        # Get missing assignments
        debrief.missing_assignments = self._get_missing_assignments()

        # Get current grades
        debrief.current_grades = self._get_current_grades()

        return debrief

    def _get_courses(self) -> List[Dict]:
        """Get active courses for the student (cached)."""
        if self._courses_cache is None:
            self._courses_cache = canvas_api.get_student_courses(self.student_id)
        return self._courses_cache

    def _get_school_days(
        self, target_date: date
    ) -> tuple[str, str, date, date]:
        """
        Get school day names, handling weekends.

        On weekends: shows Friday as "today", Monday as "tomorrow"

        Returns:
            (day_of_week, tomorrow_day, effective_today_date, effective_tomorrow_date)
        """
        weekday = target_date.weekday()  # 0=Monday, 6=Sunday

        if weekday == 5:  # Saturday
            # Show Friday and Monday
            effective_today = target_date - timedelta(days=1)
            effective_tomorrow = target_date + timedelta(days=2)
        elif weekday == 6:  # Sunday
            # Show Friday and Monday
            effective_today = target_date - timedelta(days=2)
            effective_tomorrow = target_date + timedelta(days=1)
        else:
            effective_today = target_date
            if weekday == 4:  # Friday
                effective_tomorrow = target_date + timedelta(days=3)  # Monday
            else:
                effective_tomorrow = target_date + timedelta(days=1)

        day_of_week = effective_today.strftime("%A")
        tomorrow_day = effective_tomorrow.strftime("%A")

        return day_of_week, tomorrow_day, effective_today, effective_tomorrow

    def _collect_course_agenda(
        self, course: Dict, today_date: date, tomorrow_date: date
    ) -> Optional[CourseAgenda]:
        """Collect agenda content for a single course."""
        course_id = course["id"]
        course_name = course.get("name", "Unknown Course")

        # Strategy 1: Try the front page first (teachers set this to current week)
        front_page = canvas_api.api_get(f"/courses/{course_id}/front_page")
        page_content = None

        if front_page and front_page.get("body"):
            title = front_page.get("title", "")
            # Check if front page is a weekly agenda (Q#W# pattern)
            if self.AGENDA_PAGE_PATTERN.match(title.strip()):
                page_content = front_page

        # Strategy 2: Fall back to searching for Q#W# pages
        if not page_content:
            pages = canvas_api.get_course_pages(course_id)
            agenda_page = self._find_agenda_page(pages, today_date)
            if agenda_page:
                page_content = canvas_api.get_page_content(course_id, agenda_page["url"])

        if not page_content or not page_content.get("body"):
            return None

        # Parse the agenda
        agenda = self.agenda_parser.parse(page_content["body"])

        # Get day names
        today_day_name = today_date.strftime("%A")
        tomorrow_day_name = tomorrow_date.strftime("%A")

        # Calculate yesterday (previous school day)
        yesterday_date = today_date - timedelta(days=1)
        if yesterday_date.weekday() == 6:  # Sunday -> Friday
            yesterday_date = today_date - timedelta(days=2)
        elif yesterday_date.weekday() == 5:  # Saturday -> Friday
            yesterday_date = today_date - timedelta(days=1)
        yesterday_day_name = yesterday_date.strftime("%A")

        # Build full week agendas dict for test scanning
        week_agendas = {}
        for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
            day_agenda = agenda.get_day(day)
            if day_agenda:
                week_agendas[day] = day_agenda

        return CourseAgenda(
            course_id=course_id,
            course_name=course_name,
            yesterday=agenda.get_day(yesterday_day_name),
            today=agenda.get_day(today_day_name),
            tomorrow=agenda.get_day(tomorrow_day_name),
            week_agendas=week_agendas,
        )

    def _find_agenda_page(
        self, pages: List[Dict], target_date: date
    ) -> Optional[Dict]:
        """
        Find the agenda page for the week containing target_date.

        Strategy:
        1. Find pages matching Q#W# pattern
        2. Try to match by parsing date range in page content
        3. Fall back to most recent Q#W# page
        """
        agenda_pages = []

        for page in pages:
            title = page.get("title", "")
            if self.AGENDA_PAGE_PATTERN.match(title.strip()):
                agenda_pages.append(page)

        if not agenda_pages:
            return None

        # Sort by title to get chronological order (Q1W1, Q1W2, etc.)
        agenda_pages.sort(key=lambda p: p.get("title", "").upper())

        # Calculate which week we're in based on school year
        # School year typically starts late July/early August
        # Each Q#W# corresponds to quarter and week number
        current_quarter, current_week = self._estimate_current_week(target_date)

        # Look for exact match first
        target_title = f"Q{current_quarter}W{current_week}"
        for page in agenda_pages:
            if page.get("title", "").upper() == target_title.upper():
                return page

        # Fall back to most recent page
        return agenda_pages[-1] if agenda_pages else None

    def _estimate_current_week(self, target_date: date) -> tuple[int, int]:
        """
        Estimate quarter and week number from date.

        Assumes:
        - School year starts around July 21
        - Each quarter is ~9 weeks
        - 4 quarters per year
        """
        # Rough school year start (adjust as needed)
        school_year = target_date.year
        if target_date.month < 7:
            school_year -= 1

        school_start = date(school_year, 7, 21)
        days_since_start = (target_date - school_start).days

        if days_since_start < 0:
            return 1, 1

        weeks_since_start = days_since_start // 7
        quarter = min(4, (weeks_since_start // 9) + 1)
        week_in_quarter = (weeks_since_start % 9) + 1

        return quarter, week_in_quarter

    def _get_grades_posted_today(self) -> List[Dict[str, Any]]:
        """Get grades posted in the last 24 hours."""
        recent = canvas_api.get_recent_grades(self.student_id, days=1)
        result = []

        for item in recent:
            score = item.get("score", 0)
            points = item.get("points_possible", 0)
            percentage = round((score / points * 100) if points > 0 else 0, 1)

            result.append({
                "name": item.get("assignment_name", "Unknown"),
                "course_name": item.get("course_name", "Unknown"),
                "score": score,
                "points_possible": points,
                "percentage": percentage,
            })

        return result

    def _get_announcements_today(self, courses: List[Dict]) -> List[Dict[str, Any]]:
        """Get announcements posted today across all courses."""
        today = date.today()
        today_announcements = []

        for course in courses:
            announcements = canvas_api.get_course_announcements(course["id"])
            for ann in announcements:
                posted_at = ann.get("posted_at")
                if posted_at:
                    try:
                        posted_date = datetime.strptime(
                            posted_at, "%Y-%m-%dT%H:%M:%SZ"
                        ).date()
                        if posted_date == today:
                            today_announcements.append({
                                "title": ann.get("title", "Untitled"),
                                "course_name": course.get("name", "Unknown"),
                                "message": ann.get("message", "")[:200],
                            })
                    except (ValueError, TypeError):
                        pass

        return today_announcements

    def _filter_by_due_date(
        self, assignments: List[Dict], target_date: date
    ) -> List[Dict[str, Any]]:
        """Filter assignments to those due on a specific date."""
        result = []

        for item in assignments:
            due_at = item.get("due_at")
            if due_at:
                try:
                    due_date = datetime.strptime(due_at, "%Y-%m-%dT%H:%M:%SZ").date()
                    if due_date == target_date:
                        result.append({
                            "name": item.get("name", "Unknown"),
                            "course_name": item.get("course_name", "Unknown"),
                            "points_possible": item.get("points_possible", 0),
                            "due_time": datetime.strptime(
                                due_at, "%Y-%m-%dT%H:%M:%SZ"
                            ).strftime("%I:%M %p"),
                        })
                except (ValueError, TypeError):
                    pass

        return result

    def _get_missing_assignments(self) -> List[Dict[str, Any]]:
        """Get missing assignments."""
        missing = canvas_api.get_missing_submissions(self.student_id)
        result = []

        for item in missing:
            course = item.get("course", {})
            result.append({
                "name": item.get("name", "Unknown"),
                "course_name": course.get("name", "Unknown"),
                "due_date": canvas_api.format_date(item.get("due_at")),
                "points_possible": item.get("points_possible", 0),
            })

        return result

    def _get_current_grades(self) -> List[Dict[str, Any]]:
        """Get current grades for all courses."""
        grades = canvas_api.get_all_grades(self.student_id)
        result = []

        for g in grades:
            score = g.get("current_score")
            result.append({
                "course_name": g.get("course_name", "Unknown"),
                "score": score,
                "grade": g.get("current_grade"),
            })

        result.sort(key=lambda x: x.get("score") or 0)
        return result


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/home/jasondeans/learn/canvas_api/simple_tests")

    print("Debrief Collector Test")
    print("=" * 50)

    if not canvas_api.is_api_configured():
        print("Error: Canvas API not configured")
        exit(1)

    students = canvas_api.get_students()
    if not students:
        print("No students found")
        exit(1)

    # Use first student
    student = students[0]
    print(f"Testing with: {student.get('name')}")

    collector = DebriefCollector(student["id"], student.get("name", "Unknown"))
    debrief = collector.collect()

    print(f"\nReport Date: {debrief.report_date}")
    print(f"Day of Week: {debrief.day_of_week}")
    print(f"Tomorrow: {debrief.tomorrow_day}")

    print(f"\n--- TODAY'S AGENDAS ---")
    for course_name, agenda in debrief.today_agendas.items():
        print(f"\n{course_name}:")
        if agenda.in_class:
            print(f"  In Class: {agenda.in_class[:2]}")
        if agenda.at_home:
            print(f"  At Home: {agenda.at_home[:2]}")

    print(f"\n--- TOMORROW'S AGENDAS ---")
    for course_name, agenda in debrief.tomorrow_agendas.items():
        print(f"\n{course_name}:")
        if agenda.in_class:
            print(f"  In Class: {agenda.in_class[:2]}")
        if agenda.at_home:
            print(f"  At Home: {agenda.at_home[:2]}")

    print(f"\n--- GRADES POSTED TODAY ---")
    for grade in debrief.grades_posted_today[:3]:
        print(f"  {grade['name']}: {grade['score']}/{grade['points_possible']}")

    print(f"\n--- MISSING ASSIGNMENTS ---")
    print(f"  Count: {len(debrief.missing_assignments)}")
