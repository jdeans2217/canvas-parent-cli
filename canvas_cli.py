#!/usr/bin/env python3
"""
Canvas CLI - Comprehensive tool for viewing student data
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configuration
API_URL = os.getenv("CANVAS_API_URL", "https://yourschool.instructure.com")
API_KEY = os.getenv("CANVAS_API_KEY")

if not API_KEY:
    print("Error: CANVAS_API_KEY not set in .env file")
    exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}


def api_get(endpoint, params=None):
    """Make API request."""
    url = f"{API_URL}/api/v1{endpoint}"
    try:
        resp = requests.get(url, headers=HEADERS, params=params or {}, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return None
    except:
        return None


def api_get_all(endpoint, params=None):
    """Get all pages of results."""
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
        except:
            break
    return all_results


def format_date(date_str):
    """Format ISO date to readable format."""
    if not date_str:
        return "No date"
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        return dt.strftime("%b %d, %Y")
    except:
        return date_str


def print_header(title, char="="):
    """Print a formatted header."""
    print(f"\n{char * 60}")
    print(f"  {title}")
    print(char * 60)


def print_menu(options, title=None):
    """Print numbered menu options."""
    if title:
        print(f"\n{title}")
    print("-" * 40)
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    print("  0. Back")
    print("-" * 40)


def get_choice(max_val):
    """Get user menu choice."""
    try:
        choice = input("Enter choice: ").strip()
        if choice == "0":
            return 0
        val = int(choice)
        if 1 <= val <= max_val:
            return val
    except:
        pass
    return -1


# =============================================================================
# DATA FETCHING FUNCTIONS
# =============================================================================

def get_students():
    """Get observed students."""
    data = api_get("/users/self/observees")
    return data or []


def get_student_courses(student_id, active_only=True):
    """Get courses for a student."""
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
            except:
                pass

        if not c.get("concluded", False):
            result.append(c)

    return result


def get_course_grades(course_id, student_id):
    """Get grade summary for student in course."""
    enrollments = api_get(f"/courses/{course_id}/enrollments",
                          {"user_id": student_id, "include[]": "total_scores"})
    if enrollments:
        for e in enrollments:
            if str(e.get("user_id")) == str(student_id):
                return e.get("grades", {})
    return {}


def get_course_assignments(course_id):
    """Get all assignments for a course."""
    return api_get_all(f"/courses/{course_id}/assignments", {"order_by": "due_at"})


def get_student_submissions(course_id, student_id):
    """Get student submissions with grades."""
    return api_get_all(f"/courses/{course_id}/students/submissions",
                       {"student_ids[]": student_id, "include[]": "assignment"})


def get_course_modules(course_id):
    """Get course modules."""
    modules = api_get_all(f"/courses/{course_id}/modules", {"include[]": "items"})
    return modules or []


def get_course_announcements(course_id):
    """Get course announcements."""
    # Use the announcements endpoint with context
    announcements = api_get("/announcements", {"context_codes[]": f"course_{course_id}"})
    return announcements or []


def get_course_pages(course_id):
    """Get course pages."""
    return api_get_all(f"/courses/{course_id}/pages") or []


def get_course_files(course_id):
    """Get course files."""
    return api_get_all(f"/courses/{course_id}/files") or []


def get_missing_submissions(student_id):
    """Get all missing submissions for a student."""
    return api_get(f"/users/{student_id}/missing_submissions", {"include[]": "course"}) or []


# =============================================================================
# VIEW FUNCTIONS
# =============================================================================

def view_grades_summary(student, courses):
    """View grades summary for all courses."""
    print_header(f"GRADES SUMMARY - {student['name']}")

    for course in courses:
        grades = get_course_grades(course["id"], student["id"])
        current = grades.get("current_score")
        grade = grades.get("current_grade", "")

        if current is not None:
            print(f"\n  {course['name'][:40]}")
            print(f"    Score: {current}% {grade}")
        else:
            print(f"\n  {course['name'][:40]}")
            print(f"    Score: N/A")


def view_course_grades_detail(course, student):
    """View detailed grades for a course."""
    print_header(f"GRADES - {course['name']}")

    # Get overall grade
    grades = get_course_grades(course["id"], student["id"])
    current = grades.get("current_score", "N/A")
    final = grades.get("final_score", "N/A")
    letter = grades.get("current_grade", "")

    print(f"\n  Overall: {current}% {letter}")
    print(f"  Final: {final}%")

    # Get submissions with grades
    print("\n  Recent Graded Assignments:")
    print("  " + "-" * 50)

    submissions = get_student_submissions(course["id"], student["id"])
    graded = [s for s in submissions if s.get("score") is not None]
    graded.sort(key=lambda x: x.get("graded_at") or "", reverse=True)

    for sub in graded[:15]:
        assignment = sub.get("assignment", {})
        name = assignment.get("name", "Unknown")[:35]
        score = sub.get("score", 0)
        points = assignment.get("points_possible", 0)
        pct = (score / points * 100) if points else 0

        print(f"    {name:<35} {score:>5}/{points:<5} ({pct:>5.1f}%)")

    input("\nPress Enter to continue...")


def view_course_assignments(course, student):
    """View assignments for a course."""
    print_header(f"ASSIGNMENTS - {course['name']}")

    submissions = get_student_submissions(course["id"], student["id"])
    sub_map = {s.get("assignment_id"): s for s in submissions}

    assignments = get_course_assignments(course["id"])

    # Group by status
    upcoming = []
    graded = []
    missing = []

    now = datetime.now()

    for a in assignments:
        aid = a.get("id")
        sub = sub_map.get(aid, {})
        due = a.get("due_at")

        if due:
            try:
                due_date = datetime.strptime(due, "%Y-%m-%dT%H:%M:%SZ")
                is_past = due_date < now
            except:
                is_past = False
        else:
            is_past = False

        if sub.get("score") is not None:
            graded.append((a, sub))
        elif is_past and not sub.get("submitted_at"):
            missing.append((a, sub))
        elif not is_past:
            upcoming.append((a, sub))

    # Show upcoming
    if upcoming:
        print("\n  UPCOMING:")
        for a, sub in upcoming[:10]:
            name = a.get("name", "Unknown")[:40]
            due = format_date(a.get("due_at"))
            pts = a.get("points_possible", 0)
            print(f"    {name:<40} Due: {due:<12} {pts} pts")

    # Show missing
    if missing:
        print("\n  MISSING:")
        for a, sub in missing[:10]:
            name = a.get("name", "Unknown")[:40]
            due = format_date(a.get("due_at"))
            pts = a.get("points_possible", 0)
            print(f"    {name:<40} Due: {due:<12} {pts} pts")

    # Show graded
    if graded:
        print("\n  GRADED (Recent):")
        graded.sort(key=lambda x: x[1].get("graded_at") or "", reverse=True)
        for a, sub in graded[:10]:
            name = a.get("name", "Unknown")[:35]
            score = sub.get("score", 0)
            pts = a.get("points_possible", 0)
            pct = (score / pts * 100) if pts else 0
            print(f"    {name:<35} {score:>5}/{pts:<5} ({pct:>5.1f}%)")

    input("\nPress Enter to continue...")


def view_course_modules(course):
    """View course modules."""
    print_header(f"MODULES - {course['name']}")

    modules = get_course_modules(course["id"])

    if not modules:
        print("\n  No modules found.")
    else:
        for mod in modules[:10]:
            name = mod.get("name", "Unknown")
            items = mod.get("items", [])
            state = mod.get("state", "")

            print(f"\n  📦 {name} ({len(items)} items) [{state}]")

            for item in items[:5]:
                item_name = item.get("title", "Unknown")[:50]
                item_type = item.get("type", "")
                print(f"      - {item_name} [{item_type}]")

            if len(items) > 5:
                print(f"      ... and {len(items) - 5} more items")

    input("\nPress Enter to continue...")


def view_course_announcements(course):
    """View course announcements."""
    print_header(f"ANNOUNCEMENTS - {course['name']}")

    announcements = get_course_announcements(course["id"])

    if not announcements:
        print("\n  No announcements found.")
    else:
        for ann in announcements[:10]:
            title = ann.get("title", "No title")
            posted = format_date(ann.get("posted_at"))
            author = ann.get("author", {}).get("display_name", "Unknown")

            print(f"\n  📢 {title}")
            print(f"     Posted: {posted} by {author}")

            # Get message preview
            message = ann.get("message", "")
            # Strip HTML
            import re
            text = re.sub(r'<[^>]+>', '', message)[:200]
            if text:
                print(f"     {text}...")

    input("\nPress Enter to continue...")


def view_course_files(course):
    """View course files."""
    print_header(f"FILES - {course['name']}")

    files = get_course_files(course["id"])

    if not files:
        print("\n  No files found.")
    else:
        for f in files[:20]:
            name = f.get("display_name", "Unknown")
            size = f.get("size", 0)
            size_str = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"
            modified = format_date(f.get("modified_at"))

            print(f"    📄 {name:<45} {size_str:>10}  {modified}")

    input("\nPress Enter to continue...")


def view_course_pages(course):
    """View course pages."""
    print_header(f"PAGES - {course['name']}")

    pages = get_course_pages(course["id"])

    if not pages:
        print("\n  No pages found.")
    else:
        for p in pages[:20]:
            title = p.get("title", "Untitled")
            updated = format_date(p.get("updated_at"))

            print(f"    📄 {title:<45} Updated: {updated}")

    input("\nPress Enter to continue...")


def view_missing_all(student, courses):
    """View all missing assignments across courses."""
    print_header(f"ALL MISSING ASSIGNMENTS - {student['name']}")

    missing = get_missing_submissions(student["id"])

    if not missing:
        print("\n  No missing assignments! 🎉")
    else:
        # Group by course
        by_course = {}
        for m in missing:
            course_name = m.get("course", {}).get("name", "Unknown")
            if course_name not in by_course:
                by_course[course_name] = []
            by_course[course_name].append(m)

        for course_name, items in by_course.items():
            print(f"\n  {course_name}:")
            for item in items[:10]:
                name = item.get("name", "Unknown")[:40]
                due = format_date(item.get("due_at"))
                pts = item.get("points_possible", 0)
                print(f"    - {name:<40} Due: {due} ({pts} pts)")

    input("\nPress Enter to continue...")


def view_quick_dashboard(student, courses):
    """Quick dashboard view."""
    print_header(f"DASHBOARD - {student['name']}")

    # Grades summary
    print("\n  📊 CURRENT GRADES:")
    print("  " + "-" * 50)

    for course in courses[:10]:
        grades = get_course_grades(course["id"], student["id"])
        current = grades.get("current_score")

        if current is not None:
            name = course['name'][:35]
            bar = "█" * int(current / 5) + "░" * (20 - int(current / 5))
            print(f"    {name:<35} {current:>5.1f}% {bar}")

    # Missing count
    missing = get_missing_submissions(student["id"])
    print(f"\n  📋 Missing assignments: {len(missing)}")

    if missing:
        print("\n  Most urgent:")
        sorted_missing = sorted(missing, key=lambda x: x.get("due_at") or "")
        for m in sorted_missing[:5]:
            name = m.get("name", "Unknown")[:35]
            course = m.get("course", {}).get("name", "")[:20]
            print(f"    - {name} ({course})")

    input("\nPress Enter to continue...")


# =============================================================================
# MENU FUNCTIONS
# =============================================================================

def course_menu(course, student):
    """Menu for a specific course."""
    while True:
        print_header(f"{course['name']}")

        # Show quick grade
        grades = get_course_grades(course["id"], student["id"])
        current = grades.get("current_score")
        if current:
            print(f"  Current Grade: {current}%")

        print_menu([
            "View Grades (detailed)",
            "View Assignments",
            "View Modules",
            "View Announcements",
            "View Files",
            "View Pages",
        ])

        choice = get_choice(6)

        if choice == 0:
            break
        elif choice == 1:
            view_course_grades_detail(course, student)
        elif choice == 2:
            view_course_assignments(course, student)
        elif choice == 3:
            view_course_modules(course)
        elif choice == 4:
            view_course_announcements(course)
        elif choice == 5:
            view_course_files(course)
        elif choice == 6:
            view_course_pages(course)


def student_menu(student):
    """Menu for a specific student."""
    courses = get_student_courses(student["id"])

    while True:
        print_header(f"{student['name']} - {len(courses)} Courses")

        print_menu([
            "📊 Quick Dashboard",
            "📈 View All Grades",
            "📋 View All Missing Work",
            "📚 Browse Courses",
        ], "What would you like to view?")

        choice = get_choice(4)

        if choice == 0:
            break
        elif choice == 1:
            view_quick_dashboard(student, courses)
        elif choice == 2:
            view_grades_summary(student, courses)
            input("\nPress Enter to continue...")
        elif choice == 3:
            view_missing_all(student, courses)
        elif choice == 4:
            # Course selection
            while True:
                print_header("SELECT COURSE")

                for i, c in enumerate(courses, 1):
                    grades = get_course_grades(c["id"], student["id"])
                    score = grades.get("current_score")
                    score_str = f"{score:.1f}%" if score else "N/A"
                    print(f"  {i:2}. {c['name'][:40]:<40} {score_str:>8}")

                print("\n   0. Back")
                print("-" * 60)

                course_choice = get_choice(len(courses))
                if course_choice == 0:
                    break
                elif course_choice > 0:
                    course_menu(courses[course_choice - 1], student)


def main_menu():
    """Main entry point."""
    students = get_students()

    if not students:
        print("No students found. Check your API key.")
        return

    while True:
        print_header("CANVAS CLI")
        print(f"\n  Welcome! You have access to {len(students)} students.\n")

        print("  Select a student:")
        for i, s in enumerate(students, 1):
            print(f"    {i}. {s['name']}")

        print("\n    0. Exit")
        print("-" * 40)

        choice = get_choice(len(students))

        if choice == 0:
            print("\nGoodbye!")
            break
        elif choice > 0:
            student_menu(students[choice - 1])


if __name__ == "__main__":
    main_menu()
