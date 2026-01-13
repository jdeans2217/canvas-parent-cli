#!/usr/bin/env python3
"""
Data Collector - Fetch and aggregate Canvas data for reports.

Collects grades, assignments, and other data needed for email reports.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import canvas_api


class DataCollector:
    """
    Collects and aggregates Canvas data for reports.

    Provides structured data ready for report templates.
    """

    def __init__(self, student_id: int, student_name: str):
        """
        Initialize data collector for a student.

        Args:
            student_id: Canvas user ID
            student_name: Student's display name
        """
        self.student_id = student_id
        self.student_name = student_name
        self._courses_cache: Optional[List[Dict]] = None
        self._grades_cache: Optional[List[Dict]] = None

    def get_courses(self) -> List[Dict]:
        """Get active courses for the student."""
        if self._courses_cache is None:
            self._courses_cache = canvas_api.get_student_courses(self.student_id)
        return self._courses_cache

    def get_grades(self) -> List[Dict[str, Any]]:
        """
        Get current grades for all courses.

        Returns:
            List of dicts with course info and grades
        """
        if self._grades_cache is not None:
            return self._grades_cache

        grades = canvas_api.get_all_grades(self.student_id)

        # Add grade classification
        for grade in grades:
            score = grade.get("current_score")
            grade["grade_class"] = self._get_grade_class(score)

        self._grades_cache = grades
        return grades

    def get_courses_with_grades(self) -> List[Dict[str, Any]]:
        """
        Get courses formatted for the report template.

        Returns:
            List of course dicts with name, score, grade, grade_class
        """
        grades = self.get_grades()
        result = []

        for g in grades:
            result.append({
                "name": g.get("course_name", "Unknown Course"),
                "score": g.get("current_score"),
                "grade": g.get("current_grade"),
                "grade_class": g.get("grade_class", ""),
            })

        # Sort by grade (lowest first for attention)
        result.sort(key=lambda x: x.get("score") or 0)
        return result

    def get_missing_assignments(self) -> List[Dict[str, Any]]:
        """
        Get missing assignments for the student.

        Returns:
            List of missing assignment dicts
        """
        missing = canvas_api.get_missing_submissions(self.student_id)
        result = []

        for item in missing:
            course = item.get("course", {})
            result.append({
                "name": item.get("name", "Unknown Assignment"),
                "course_name": course.get("name", "Unknown Course"),
                "due_date": canvas_api.format_date(item.get("due_at")),
                "points_possible": item.get("points_possible", 0),
            })

        return result

    def get_upcoming_assignments(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get upcoming assignments.

        Args:
            days: Number of days to look ahead

        Returns:
            List of upcoming assignment dicts with urgency classification
        """
        upcoming = canvas_api.get_upcoming_assignments(self.student_id, days)
        result = []
        now = datetime.now()

        for item in upcoming:
            due_at = item.get("due_at")
            urgency_class = ""

            if due_at:
                try:
                    due_date = datetime.strptime(due_at, "%Y-%m-%dT%H:%M:%SZ")
                    days_until = (due_date - now).days

                    if days_until <= 0:
                        urgency_class = "due-today"
                    elif days_until == 1:
                        urgency_class = "due-tomorrow"
                    else:
                        urgency_class = "due-soon"
                except Exception:
                    pass

            result.append({
                "name": item.get("name", "Unknown Assignment"),
                "course_name": item.get("course_name", "Unknown Course"),
                "due_date": canvas_api.format_date(due_at),
                "points_possible": item.get("points_possible", 0),
                "urgency_class": urgency_class,
            })

        return result

    def get_recent_grades(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get recently graded assignments.

        Args:
            days: Number of days to look back

        Returns:
            List of recently graded assignment dicts
        """
        recent = canvas_api.get_recent_grades(self.student_id, days)
        result = []

        for item in recent:
            score = item.get("score", 0)
            points = item.get("points_possible", 0)
            percentage = round((score / points * 100) if points > 0 else 0, 1)

            result.append({
                "name": item.get("assignment_name", "Unknown Assignment"),
                "course_name": item.get("course_name", "Unknown Course"),
                "score": score,
                "points_possible": points,
                "percentage": percentage,
                "graded_date": canvas_api.format_date(item.get("graded_at")),
            })

        return result

    def get_grade_alerts(self, threshold: int = 80) -> List[Dict[str, str]]:
        """
        Get alerts for courses below grade threshold.

        Args:
            threshold: Grade percentage threshold for alerts

        Returns:
            List of alert dicts with course and message
        """
        grades = self.get_grades()
        alerts = []

        for grade in grades:
            score = grade.get("current_score")
            if score is not None and score < threshold:
                alerts.append({
                    "course": grade.get("course_name", "Unknown Course"),
                    "message": f"Grade is {score}%, below the {threshold}% threshold",
                })

        return alerts

    def get_average_grade(self) -> Optional[float]:
        """Calculate average grade across all courses."""
        grades = self.get_grades()
        scores = [g.get("current_score") for g in grades if g.get("current_score") is not None]

        if not scores:
            return None

        return round(sum(scores) / len(scores), 1)

    def get_report_data(self, grade_alert_threshold: int = 80) -> Dict[str, Any]:
        """
        Get all data needed for the daily report.

        Args:
            grade_alert_threshold: Threshold for grade alerts

        Returns:
            Complete data dict for report template
        """
        courses = self.get_courses_with_grades()
        missing = self.get_missing_assignments()
        upcoming = self.get_upcoming_assignments()
        recent = self.get_recent_grades()
        alerts = self.get_grade_alerts(grade_alert_threshold)
        avg_grade = self.get_average_grade()

        return {
            "student_name": self.student_name,
            "report_date": datetime.now().strftime("%A, %B %d, %Y"),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),

            # Stats
            "courses": courses,
            "missing_count": len(missing),
            "upcoming_count": len(upcoming),
            "average_grade": avg_grade,
            "average_grade_class": self._get_grade_class(avg_grade) if avg_grade else "",

            # Details
            "missing_assignments": missing,
            "upcoming_assignments": upcoming,
            "recent_grades": recent,
            "grade_alerts": alerts,

            # Chart flag (set by report builder)
            "grades_chart": False,
        }

    @staticmethod
    def _get_grade_class(score: Optional[float]) -> str:
        """Get CSS class for grade coloring."""
        if score is None:
            return ""
        if score >= 90:
            return "grade-a"
        if score >= 80:
            return "grade-b"
        if score >= 70:
            return "grade-c"
        if score >= 60:
            return "grade-d"
        return "grade-f"


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    import json

    print("Data Collector Test")
    print("=" * 50)

    if not canvas_api.is_api_configured():
        print("Error: Canvas API not configured")
        exit(1)

    students = canvas_api.get_students()
    if not students:
        print("No students found")
        exit(1)

    # Use first student for testing
    student = students[0]
    print(f"Testing with student: {student.get('name')}")

    collector = DataCollector(student["id"], student.get("name", "Unknown"))
    data = collector.get_report_data()

    print(f"\nReport Data Summary:")
    print(f"  Courses: {len(data['courses'])}")
    print(f"  Missing: {data['missing_count']}")
    print(f"  Upcoming: {data['upcoming_count']}")
    print(f"  Average Grade: {data['average_grade']}%")

    print(f"\nGrade Alerts: {len(data['grade_alerts'])}")
    for alert in data["grade_alerts"]:
        print(f"  - {alert['course']}: {alert['message']}")
