#!/usr/bin/env python3
"""
Sync Calendar CLI - Sync Canvas assignments to Google Calendar.

Usage:
    python -m cli.sync_calendar                  # Sync all students
    python -m cli.sync_calendar --student "JJ"   # Sync specific student
    python -m cli.sync_calendar --list           # List available calendars
    python -m cli.sync_calendar --cleanup        # Remove old events

Options:
    --student NAME    Sync only specific student
    --list            List available Google Calendars
    --cleanup         Remove events older than 30 days
    --days DAYS       Days of assignments to sync (default: 30)
    --color-by TYPE   Color events by 'course' or 'urgency' (default: course)
    --calendar-id ID  Use specific calendar ID instead of creating one
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from typing import Optional, List, Dict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import canvas_api
from config import get_config
from google_services.calendar_service import CalendarService, AssignmentSync


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Sync Canvas assignments to Google Calendar",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--student",
        type=str,
        help="Sync only specific student (by name)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available Google Calendars",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove events older than 30 days",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Days of assignments to sync (default: 30)",
    )
    parser.add_argument(
        "--color-by",
        choices=["course", "urgency"],
        default="course",
        help="Color events by course or urgency (default: course)",
    )
    parser.add_argument(
        "--calendar-id",
        type=str,
        help="Use specific calendar ID",
    )

    return parser.parse_args()


def list_calendars():
    """List all available Google Calendars."""
    print("Fetching calendars...")

    try:
        calendar = CalendarService()
        calendars = calendar.list_calendars()

        print(f"\nFound {len(calendars)} calendar(s):\n")
        for cal in calendars:
            name = cal.get("summary", "Unnamed")
            cal_id = cal.get("id", "")
            primary = " (primary)" if cal.get("primary") else ""
            access = cal.get("accessRole", "")

            print(f"  {name}{primary}")
            print(f"    ID: {cal_id}")
            print(f"    Access: {access}")
            print()

        return True

    except Exception as e:
        print(f"Error listing calendars: {e}")
        return False


def get_student_assignments(student_id: int, days: int) -> List[Dict]:
    """
    Get all assignments for a student within the specified days.

    Args:
        student_id: Canvas student ID
        days: Number of days to look ahead

    Returns:
        List of assignment dicts with course info
    """
    assignments = []
    courses = canvas_api.get_student_courses(student_id)

    for course in courses:
        course_assignments = canvas_api.get_course_assignments(course["id"])

        for assignment in course_assignments:
            due_at = assignment.get("due_at")
            if not due_at:
                continue

            try:
                due_date = datetime.strptime(due_at, "%Y-%m-%dT%H:%M:%SZ")
                now = datetime.now()

                # Include assignments from past week to future days
                if (due_date >= now - timedelta(days=7) and
                    due_date <= now + timedelta(days=days)):
                    assignment["course_name"] = course.get("name", "Unknown")
                    assignment["course_id"] = course["id"]
                    assignments.append(assignment)
            except Exception:
                continue

    return assignments


def sync_student(
    student_id: int,
    student_name: str,
    days: int,
    color_by: str,
    calendar_id: Optional[str] = None,
) -> bool:
    """
    Sync assignments for a single student.

    Args:
        student_id: Canvas student ID
        student_name: Student's display name
        days: Days of assignments to sync
        color_by: Color coding method
        calendar_id: Optional specific calendar ID

    Returns:
        True if sync was successful
    """
    print(f"\nSyncing: {student_name}")
    print("-" * 40)

    try:
        # Get assignments
        print("  Fetching assignments from Canvas...")
        assignments = get_student_assignments(student_id, days)
        print(f"  Found {len(assignments)} assignments")

        if not assignments:
            print("  No assignments to sync")
            return True

        # Sync to calendar
        print("  Syncing to Google Calendar...")
        sync = AssignmentSync(color_by=color_by)
        stats = sync.sync_assignments(
            student_id=student_id,
            student_name=student_name,
            assignments=assignments,
            calendar_id=calendar_id,
        )

        print(f"  Created: {stats['created']}")
        print(f"  Updated: {stats['updated']}")
        print(f"  Skipped: {stats['skipped']} (no due date)")

        return True

    except Exception as e:
        print(f"  Error: {e}")
        return False


def cleanup_calendars(student_name: Optional[str] = None) -> bool:
    """
    Remove old events from student calendars.

    Args:
        student_name: Optional specific student

    Returns:
        True if cleanup was successful
    """
    print("Cleaning up old events...")

    try:
        calendar = CalendarService()
        sync = AssignmentSync(calendar_service=calendar)

        # Find Canvas calendars
        calendars = calendar.list_calendars()
        canvas_calendars = [
            c for c in calendars
            if "Canvas" in c.get("summary", "")
        ]

        if student_name:
            canvas_calendars = [
                c for c in canvas_calendars
                if student_name.lower() in c.get("summary", "").lower()
            ]

        if not canvas_calendars:
            print("No Canvas calendars found")
            return True

        total_deleted = 0
        for cal in canvas_calendars:
            cal_name = cal.get("summary", "Unknown")
            print(f"\n  Cleaning: {cal_name}")

            deleted = sync.cleanup_old_events(cal["id"], days_old=30)
            print(f"  Deleted {deleted} old events")
            total_deleted += deleted

        print(f"\nTotal deleted: {total_deleted}")
        return True

    except Exception as e:
        print(f"Error during cleanup: {e}")
        return False


def main():
    """Main entry point."""
    args = parse_args()

    print("Canvas Parent CLI - Calendar Sync")
    print("=" * 50)

    # Handle list command
    if args.list:
        success = list_calendars()
        sys.exit(0 if success else 1)

    # Handle cleanup command
    if args.cleanup:
        success = cleanup_calendars(args.student)
        sys.exit(0 if success else 1)

    # Check Canvas API configuration
    if not canvas_api.is_api_configured():
        print("Error: Canvas API not configured")
        print("Set CANVAS_API_URL and CANVAS_API_KEY in .env file")
        sys.exit(1)

    # Get students
    students = canvas_api.get_students()
    if not students:
        print("No students found")
        sys.exit(1)

    print(f"Found {len(students)} student(s)")

    # Filter by student name if specified
    if args.student:
        students = [
            s for s in students
            if args.student.lower() in s.get("name", "").lower()
        ]
        if not students:
            print(f"No student found matching '{args.student}'")
            sys.exit(1)

    # Get config for calendar IDs
    config = get_config()

    # Sync each student
    success_count = 0
    for student in students:
        student_id = student["id"]
        student_name = student.get("name", "Unknown")

        # Check for configured calendar ID
        calendar_id = args.calendar_id
        if not calendar_id:
            # Check config for student-specific calendar
            student_key = str(student_id)
            calendar_id = config.calendar.student_calendars.get(student_key)

        if sync_student(
            student_id,
            student_name,
            args.days,
            args.color_by,
            calendar_id,
        ):
            success_count += 1

    # Summary
    print(f"\n{'=' * 50}")
    print(f"Completed: {success_count}/{len(students)} students")

    if success_count == len(students):
        print("\nCalendars have been synced!")
        print("Check your Google Calendar for the new events.")

    sys.exit(0 if success_count == len(students) else 1)


if __name__ == "__main__":
    main()
