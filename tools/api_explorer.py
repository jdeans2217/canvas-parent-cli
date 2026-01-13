#!/usr/bin/env python3
"""
Canvas API Explorer - Discover available endpoints and data
"""

import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("CANVAS_API_URL", "https://yourschool.instructure.com")
API_KEY = os.getenv("CANVAS_API_KEY")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}

# Common Canvas API endpoints to test
ENDPOINTS = {
    "User & Account": [
        ("/users/self", "Current user profile"),
        ("/users/self/profile", "User profile details"),
        ("/users/self/settings", "User settings"),
        ("/users/self/observees", "Observed students (for parents)"),
        ("/users/self/courses", "User's courses"),
        ("/users/self/favorites/courses", "Favorite courses"),
        ("/users/self/enrollments", "User enrollments"),
        ("/users/self/calendar_events", "Calendar events"),
        ("/users/self/upcoming_events", "Upcoming events"),
        ("/users/self/missing_submissions", "Missing submissions"),
        ("/users/self/todo", "To-do items"),
        ("/users/self/activity_stream", "Activity stream"),
        ("/users/self/communication_channels", "Communication channels"),
    ],
    "Courses": [
        ("/courses", "All accessible courses"),
        ("/dashboard/dashboard_cards", "Dashboard course cards"),
    ],
    "Announcements & Conversations": [
        ("/announcements", "Announcements"),
        ("/conversations", "Conversations/messages"),
        ("/conversations/unread_count", "Unread message count"),
    ],
    "Calendar": [
        ("/calendar_events", "Calendar events"),
        ("/planner/items", "Planner items"),
        ("/planner/overrides", "Planner overrides"),
    ],
    "Grades & Progress": [
        ("/users/self/grades", "User grades"),
        ("/progress", "Progress items"),
    ],
    "Other": [
        ("/brand_variables", "Brand/theme variables"),
        ("/accounts", "Accounts"),
        ("/appointment_groups", "Appointment groups"),
    ],
}

# Course-specific endpoints (need course_id)
COURSE_ENDPOINTS = [
    ("/courses/{course_id}", "Course details"),
    ("/courses/{course_id}/assignments", "Assignments"),
    ("/courses/{course_id}/assignment_groups", "Assignment groups"),
    ("/courses/{course_id}/modules", "Modules"),
    ("/courses/{course_id}/announcements", "Course announcements"),
    ("/courses/{course_id}/discussion_topics", "Discussion topics"),
    ("/courses/{course_id}/files", "Course files"),
    ("/courses/{course_id}/folders", "Course folders"),
    ("/courses/{course_id}/pages", "Wiki pages"),
    ("/courses/{course_id}/quizzes", "Quizzes"),
    ("/courses/{course_id}/enrollments", "Course enrollments"),
    ("/courses/{course_id}/users", "Course users"),
    ("/courses/{course_id}/grades", "Course grades"),
    ("/courses/{course_id}/gradebook_history", "Gradebook history"),
    ("/courses/{course_id}/activity_stream", "Course activity"),
    ("/courses/{course_id}/todo", "Course to-do items"),
    ("/courses/{course_id}/tabs", "Course navigation tabs"),
    ("/courses/{course_id}/front_page", "Course front page"),
    ("/courses/{course_id}/settings", "Course settings"),
    ("/courses/{course_id}/student_view_student", "Student view"),
    ("/courses/{course_id}/external_tools", "External tools (LTI)"),
    ("/courses/{course_id}/features", "Course features"),
]

# Student-specific endpoints
STUDENT_ENDPOINTS = [
    ("/users/{student_id}/courses", "Student courses"),
    ("/users/{student_id}/enrollments", "Student enrollments"),
    ("/users/{student_id}/missing_submissions", "Missing submissions"),
    ("/users/{student_id}/calendar_events", "Student calendar"),
]


def test_endpoint(endpoint, description=""):
    """Test if an endpoint is accessible and return sample data."""
    url = f"{API_URL}/api/v1{endpoint}"
    try:
        response = requests.get(url, headers=HEADERS, params={"per_page": 5})
        status = response.status_code

        if status == 200:
            data = response.json()
            if isinstance(data, list):
                count = len(data)
                return {"status": "OK", "type": "list", "count": count, "sample": data[:2] if data else []}
            elif isinstance(data, dict):
                return {"status": "OK", "type": "object", "keys": list(data.keys())[:10]}
            else:
                return {"status": "OK", "type": type(data).__name__}
        elif status == 401:
            return {"status": "UNAUTHORIZED"}
        elif status == 403:
            return {"status": "FORBIDDEN"}
        elif status == 404:
            return {"status": "NOT_FOUND"}
        else:
            return {"status": f"ERROR_{status}"}
    except Exception as e:
        return {"status": f"EXCEPTION: {str(e)[:50]}"}


def explore_general_endpoints():
    """Test all general endpoints."""
    print("\n" + "=" * 60)
    print("CANVAS API ENDPOINT EXPLORER")
    print("=" * 60)

    accessible = []

    for category, endpoints in ENDPOINTS.items():
        print(f"\n--- {category} ---")
        for endpoint, description in endpoints:
            result = test_endpoint(endpoint)
            status = result["status"]

            if status == "OK":
                accessible.append((endpoint, description, result))
                if result.get("type") == "list":
                    print(f"  [OK] {endpoint} - {description} ({result['count']} items)")
                else:
                    print(f"  [OK] {endpoint} - {description}")
            else:
                print(f"  [{status}] {endpoint}")

    return accessible


def explore_course_endpoints(course_id):
    """Test course-specific endpoints."""
    print(f"\n--- Course {course_id} Endpoints ---")

    accessible = []
    for endpoint_template, description in COURSE_ENDPOINTS:
        endpoint = endpoint_template.format(course_id=course_id)
        result = test_endpoint(endpoint)
        status = result["status"]

        if status == "OK":
            accessible.append((endpoint, description, result))
            if result.get("type") == "list":
                print(f"  [OK] {endpoint} - {description} ({result['count']} items)")
            else:
                print(f"  [OK] {endpoint} - {description}")
        else:
            print(f"  [{status}] {endpoint}")

    return accessible


def explore_student_endpoints(student_id):
    """Test student-specific endpoints."""
    print(f"\n--- Student {student_id} Endpoints ---")

    accessible = []
    for endpoint_template, description in STUDENT_ENDPOINTS:
        endpoint = endpoint_template.format(student_id=student_id)
        result = test_endpoint(endpoint)
        status = result["status"]

        if status == "OK":
            accessible.append((endpoint, description, result))
            if result.get("type") == "list":
                print(f"  [OK] {endpoint} - {description} ({result['count']} items)")
            else:
                print(f"  [OK] {endpoint} - {description}")
        else:
            print(f"  [{status}] {endpoint}")

    return accessible


def raw_api_call(endpoint):
    """Make a raw API call and show full response."""
    url = f"{API_URL}/api/v1{endpoint}"
    print(f"\nGET {url}")
    print("-" * 60)

    try:
        response = requests.get(url, headers=HEADERS, params={"per_page": 10})
        print(f"Status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type', 'unknown')}")

        if 'application/json' in response.headers.get('Content-Type', ''):
            data = response.json()
            print("\nResponse (formatted JSON):")
            print(json.dumps(data, indent=2)[:3000])
            if len(json.dumps(data)) > 3000:
                print("\n... (truncated)")
        else:
            print("\nResponse (raw):")
            print(response.text[:1000])
    except Exception as e:
        print(f"Error: {e}")


def interactive_explorer():
    """Interactive mode for exploring the API."""
    print("\n" + "=" * 60)
    print("INTERACTIVE API EXPLORER")
    print("=" * 60)
    print("\nCommands:")
    print("  1. Scan all general endpoints")
    print("  2. Scan course endpoints (pick a course)")
    print("  3. Scan student endpoints (pick a student)")
    print("  4. Raw API call (enter any endpoint)")
    print("  5. Show accessible endpoints summary")
    print("  0. Exit")

    all_accessible = []

    while True:
        choice = input("\nEnter choice: ").strip()

        if choice == "0":
            break
        elif choice == "1":
            accessible = explore_general_endpoints()
            all_accessible.extend(accessible)
        elif choice == "2":
            # Get a course ID
            courses = test_endpoint("/users/self/courses")
            if courses["status"] == "OK" and courses.get("sample"):
                print("\nSample courses:")
                for i, c in enumerate(courses["sample"][:5], 1):
                    print(f"  {i}. {c.get('name', 'Unknown')} (ID: {c.get('id')})")
            course_id = input("Enter course ID: ").strip()
            if course_id:
                accessible = explore_course_endpoints(course_id)
                all_accessible.extend(accessible)
        elif choice == "3":
            # Get students
            students = test_endpoint("/users/self/observees")
            if students["status"] == "OK" and students.get("sample"):
                print("\nStudents:")
                for s in students["sample"]:
                    print(f"  - {s.get('name')} (ID: {s.get('id')})")
            student_id = input("Enter student ID: ").strip()
            if student_id:
                accessible = explore_student_endpoints(student_id)
                all_accessible.extend(accessible)
        elif choice == "4":
            endpoint = input("Enter endpoint (e.g., /users/self): ").strip()
            if endpoint:
                if not endpoint.startswith("/"):
                    endpoint = "/" + endpoint
                raw_api_call(endpoint)
        elif choice == "5":
            print("\n--- ACCESSIBLE ENDPOINTS SUMMARY ---")
            for endpoint, description, result in all_accessible:
                print(f"  {endpoint} - {description}")
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    interactive_explorer()
