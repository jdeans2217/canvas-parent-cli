#!/usr/bin/env python3
"""
Canvas API Layer - Reusable API functions for Canvas LMS integration

This module provides the core API functions for interacting with Canvas LMS.
It supports pagination, error handling, and all common Canvas operations.
"""

import os
import requests
from datetime import datetime
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

# Configuration
API_URL = os.getenv("CANVAS_API_URL", "https://yourschool.instructure.com")
API_KEY = os.getenv("CANVAS_API_KEY")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}


class CanvasAPIError(Exception):
    """Custom exception for Canvas API errors."""
    pass


def api_get(endpoint: str, params: Optional[Dict] = None) -> Optional[Any]:
    """
    Make a single API GET request.

    Args:
        endpoint: API endpoint path (e.g., "/users/self")
        params: Optional query parameters

    Returns:
        JSON response data or None on failure
    """
    url = f"{API_URL}/api/v1{endpoint}"
    try:
        resp = requests.get(url, headers=HEADERS, params=params or {}, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def api_get_all(endpoint: str, params: Optional[Dict] = None) -> List[Any]:
    """
    Get all pages of results from a paginated API endpoint.

    Args:
        endpoint: API endpoint path
        params: Optional query parameters

    Returns:
        List of all results across all pages
    """
    all_results = []
    params = params or {}
    params["per_page"] = 100

    url = f"{API_URL}/api/v1{endpoint}"
    while url:
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
            if resp.status_code != 200:
                break
            data = resp.json()
            if isinstance(data, list):
                all_results.extend(data)
            else:
                all_results.append(data)

            # Check for next page
            links = resp.headers.get("Link", "")
            next_url = None
            for link in links.split(","):
                if 'rel="next"' in link:
                    next_url = link.split(";")[0].strip("<> ")
                    break
            url = next_url
            params = {}  # Params are in the URL now
        except Exception:
            break
    return all_results


# =============================================================================
# STUDENT & USER FUNCTIONS
# =============================================================================

def get_students() -> List[Dict]:
    """
    Get observed students for the current user (parent/observer).

    Returns:
        List of student objects with id and name
    """
    data = api_get("/users/self/observees")
    return data or []


def get_current_user() -> Optional[Dict]:
    """
    Get the current authenticated user.

    Returns:
        User object with id, name, email, etc.
    """
    return api_get("/users/self")


# =============================================================================
# COURSE FUNCTIONS
# =============================================================================

def get_student_courses(student_id: int, active_only: bool = True) -> List[Dict]:
    """
    Get courses for a student.

    Args:
        student_id: Canvas user ID
        active_only: If True, only return active/current courses

    Returns:
        List of course objects
    """
    params = {"include[]": "term", "per_page": 100}
    if active_only:
        params["enrollment_state"] = "active"

    courses = api_get(f"/users/{student_id}/courses", params)
    if not courses:
        return []

    # Filter current term courses
    now = datetime.now()
    result = []
    for c in courses:
        term = c.get("term", {})
        end_at = term.get("end_at")

        if end_at:
            try:
                end_date = datetime.strptime(end_at, "%Y-%m-%dT%H:%M:%SZ")
                if end_date < now:
                    continue
            except Exception:
                pass

        if not c.get("concluded", False):
            result.append(c)

    return result


def get_course(course_id: int) -> Optional[Dict]:
    """
    Get a single course by ID.

    Args:
        course_id: Canvas course ID

    Returns:
        Course object or None
    """
    return api_get(f"/courses/{course_id}")


# =============================================================================
# GRADES & ENROLLMENTS
# =============================================================================

def get_course_grades(course_id: int, student_id: int) -> Dict:
    """
    Get grade summary for a student in a course.

    Args:
        course_id: Canvas course ID
        student_id: Canvas user ID

    Returns:
        Grades dict with current_score, current_grade, final_score
    """
    enrollments = api_get(
        f"/courses/{course_id}/enrollments",
        {"user_id": student_id, "include[]": "total_scores"}
    )
    if enrollments:
        for e in enrollments:
            if str(e.get("user_id")) == str(student_id):
                return e.get("grades", {})
    return {}


def get_all_grades(student_id: int) -> List[Dict]:
    """
    Get grades for all courses for a student.

    Args:
        student_id: Canvas user ID

    Returns:
        List of dicts with course info and grades
    """
    courses = get_student_courses(student_id)
    results = []
    for course in courses:
        grades = get_course_grades(course["id"], student_id)
        results.append({
            "course_id": course["id"],
            "course_name": course.get("name", "Unknown"),
            "current_score": grades.get("current_score"),
            "current_grade": grades.get("current_grade"),
            "final_score": grades.get("final_score"),
        })
    return results


# =============================================================================
# ASSIGNMENTS
# =============================================================================

def get_course_assignments(course_id: int) -> List[Dict]:
    """
    Get all assignments for a course.

    Args:
        course_id: Canvas course ID

    Returns:
        List of assignment objects ordered by due date
    """
    return api_get_all(f"/courses/{course_id}/assignments", {"order_by": "due_at"})


def get_upcoming_assignments(student_id: int, days: int = 7) -> List[Dict]:
    """
    Get upcoming assignments across all courses.

    Args:
        student_id: Canvas user ID
        days: Number of days to look ahead

    Returns:
        List of assignments due within the specified days
    """
    from datetime import timedelta

    courses = get_student_courses(student_id)
    now = datetime.now()
    cutoff = now + timedelta(days=days)
    upcoming = []

    for course in courses:
        assignments = get_course_assignments(course["id"])
        for a in assignments:
            due_at = a.get("due_at")
            if due_at:
                try:
                    due_date = datetime.strptime(due_at, "%Y-%m-%dT%H:%M:%SZ")
                    if now <= due_date <= cutoff:
                        upcoming.append({
                            **a,
                            "course_name": course.get("name", "Unknown"),
                            "course_id": course["id"]
                        })
                except Exception:
                    pass

    # Sort by due date
    upcoming.sort(key=lambda x: x.get("due_at", ""))
    return upcoming


# =============================================================================
# SUBMISSIONS
# =============================================================================

def get_student_submissions(course_id: int, student_id: int) -> List[Dict]:
    """
    Get student submissions with grades for a course.

    Args:
        course_id: Canvas course ID
        student_id: Canvas user ID

    Returns:
        List of submission objects including assignment details
    """
    return api_get_all(
        f"/courses/{course_id}/students/submissions",
        {"student_ids[]": student_id, "include[]": "assignment"}
    )


def get_missing_submissions(student_id: int) -> List[Dict]:
    """
    Get all missing submissions for a student across all courses.

    Args:
        student_id: Canvas user ID

    Returns:
        List of missing assignment objects with course info
    """
    return api_get(
        f"/users/{student_id}/missing_submissions",
        {"include[]": "course"}
    ) or []


def get_recent_grades(student_id: int, days: int = 7) -> List[Dict]:
    """
    Get recently graded submissions across all courses.

    Args:
        student_id: Canvas user ID
        days: Number of days to look back

    Returns:
        List of recently graded submissions
    """
    from datetime import timedelta

    courses = get_student_courses(student_id)
    now = datetime.now()
    cutoff = now - timedelta(days=days)
    recent = []

    for course in courses:
        submissions = get_student_submissions(course["id"], student_id)
        for sub in submissions:
            graded_at = sub.get("graded_at")
            if graded_at and sub.get("score") is not None:
                try:
                    graded_date = datetime.strptime(graded_at, "%Y-%m-%dT%H:%M:%SZ")
                    if graded_date >= cutoff:
                        assignment = sub.get("assignment", {})
                        recent.append({
                            "assignment_name": assignment.get("name", "Unknown"),
                            "course_name": course.get("name", "Unknown"),
                            "score": sub.get("score"),
                            "points_possible": assignment.get("points_possible"),
                            "graded_at": graded_at,
                        })
                except Exception:
                    pass

    # Sort by graded date, most recent first
    recent.sort(key=lambda x: x.get("graded_at", ""), reverse=True)
    return recent


# =============================================================================
# MODULES & CONTENT
# =============================================================================

def get_course_modules(course_id: int) -> List[Dict]:
    """
    Get course modules with items.

    Args:
        course_id: Canvas course ID

    Returns:
        List of module objects with items
    """
    modules = api_get_all(f"/courses/{course_id}/modules", {"include[]": "items"})
    return modules or []


def get_course_announcements(course_id: int) -> List[Dict]:
    """
    Get course announcements.

    Args:
        course_id: Canvas course ID

    Returns:
        List of announcement objects
    """
    announcements = api_get("/announcements", {"context_codes[]": f"course_{course_id}"})
    return announcements or []


def get_course_pages(course_id: int) -> List[Dict]:
    """
    Get course wiki pages.

    Args:
        course_id: Canvas course ID

    Returns:
        List of page objects
    """
    return api_get_all(f"/courses/{course_id}/pages") or []


# =============================================================================
# FILES
# =============================================================================

def get_course_files(course_id: int) -> List[Dict]:
    """
    Get course files.

    Args:
        course_id: Canvas course ID

    Returns:
        List of file objects with url, display_name, size, etc.
    """
    return api_get_all(f"/courses/{course_id}/files") or []


def download_file(file_url: str) -> Optional[bytes]:
    """
    Download a file from Canvas.

    Args:
        file_url: URL to the file

    Returns:
        File bytes or None on failure
    """
    try:
        resp = requests.get(file_url, headers=HEADERS, timeout=60)
        if resp.status_code == 200:
            return resp.content
        return None
    except Exception:
        return None


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def format_date(date_str: Optional[str]) -> str:
    """
    Format ISO date to readable format.

    Args:
        date_str: ISO format date string

    Returns:
        Formatted date string (e.g., "Jan 15, 2025")
    """
    if not date_str:
        return "No date"
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        return dt.strftime("%b %d, %Y")
    except Exception:
        return date_str


def is_api_configured() -> bool:
    """
    Check if the API is properly configured.

    Returns:
        True if API URL and key are set
    """
    return bool(API_URL and API_KEY)


def test_connection() -> bool:
    """
    Test the API connection.

    Returns:
        True if connection is successful
    """
    user = get_current_user()
    return user is not None


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    print("Canvas API Module")
    print("=" * 40)

    if not is_api_configured():
        print("Error: API not configured. Set CANVAS_API_URL and CANVAS_API_KEY in .env")
        exit(1)

    print(f"API URL: {API_URL}")
    print(f"Testing connection...")

    if test_connection():
        user = get_current_user()
        print(f"Connected as: {user.get('name', 'Unknown')}")

        students = get_students()
        print(f"\nObserved students: {len(students)}")
        for s in students:
            print(f"  - {s.get('name')} (ID: {s.get('id')})")
    else:
        print("Connection failed. Check your API key.")
