#!/usr/bin/env python3
"""
Google Calendar Service - Sync Canvas assignments to Google Calendar.

Creates and manages calendar events for assignment due dates.
Supports per-student calendars with course color-coding.
"""

import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

from google_services.auth import GoogleAuth


# Google Calendar color IDs (1-11)
# https://developers.google.com/calendar/api/v3/reference/colors
CALENDAR_COLORS = {
    1: "lavender",
    2: "sage",
    3: "grape",
    4: "flamingo",
    5: "banana",
    6: "tangerine",
    7: "peacock",
    8: "graphite",
    9: "blueberry",
    10: "basil",
    11: "tomato",
}

# Color assignments for courses (rotate through available colors)
COURSE_COLOR_ROTATION = [9, 10, 5, 3, 7, 6, 4, 2, 1, 11, 8]

# Urgency-based colors
URGENCY_COLORS = {
    "overdue": 11,      # Tomato (red)
    "today": 6,         # Tangerine (orange)
    "tomorrow": 5,      # Banana (yellow)
    "this_week": 9,     # Blueberry (blue)
    "later": 2,         # Sage (green)
}


class CalendarService:
    """
    Google Calendar API service wrapper.

    Provides methods for syncing Canvas assignments to Google Calendar.
    """

    def __init__(self, auth: Optional[GoogleAuth] = None):
        """
        Initialize Calendar service.

        Args:
            auth: GoogleAuth instance (creates one if not provided)
        """
        self._auth = auth or GoogleAuth()
        self._service = None
        self._course_colors: Dict[str, int] = {}

    @property
    def service(self):
        """Get the Calendar API service (lazy load)."""
        if self._service is None:
            self._service = self._auth.get_service("calendar")
        return self._service

    def list_calendars(self) -> List[Dict[str, Any]]:
        """
        List all calendars accessible to the user.

        Returns:
            List of calendar dicts with id, summary, etc.
        """
        calendars = []
        page_token = None

        while True:
            result = self.service.calendarList().list(
                pageToken=page_token
            ).execute()

            calendars.extend(result.get("items", []))
            page_token = result.get("nextPageToken")

            if not page_token:
                break

        return calendars

    def get_or_create_calendar(
        self,
        name: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get an existing calendar by name or create a new one.

        Args:
            name: Calendar name/summary
            description: Optional calendar description

        Returns:
            Calendar dict with id, summary, etc.
        """
        # Check if calendar already exists
        calendars = self.list_calendars()
        for cal in calendars:
            if cal.get("summary") == name:
                return cal

        # Create new calendar
        calendar_body = {
            "summary": name,
            "description": description or f"Canvas assignments for {name}",
            "timeZone": self._get_timezone(),
        }

        created = self.service.calendars().insert(body=calendar_body).execute()
        return created

    def get_student_calendar(
        self,
        student_name: str,
        calendar_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get or create a calendar for a student.

        Args:
            student_name: Student's display name
            calendar_id: Optional specific calendar ID to use

        Returns:
            Calendar dict
        """
        if calendar_id:
            # Use specified calendar
            try:
                return self.service.calendars().get(calendarId=calendar_id).execute()
            except Exception:
                pass  # Fall through to create

        # Create/get calendar named after student
        return self.get_or_create_calendar(
            name=f"{student_name} - Canvas",
            description=f"Canvas LMS assignments for {student_name}",
        )

    def create_event(
        self,
        calendar_id: str,
        title: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        description: Optional[str] = None,
        color_id: Optional[int] = None,
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a calendar event.

        Args:
            calendar_id: Calendar ID to add event to
            title: Event title
            start_time: Event start datetime
            end_time: Event end datetime (defaults to 1 hour after start)
            description: Event description
            color_id: Google Calendar color ID (1-11)
            event_id: Optional custom event ID for idempotent creation

        Returns:
            Created event dict
        """
        if end_time is None:
            end_time = start_time + timedelta(hours=1)

        event_body = {
            "summary": title,
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": self._get_timezone(),
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": self._get_timezone(),
            },
        }

        if description:
            event_body["description"] = description

        if color_id:
            event_body["colorId"] = str(color_id)

        if event_id:
            event_body["id"] = event_id

        return self.service.events().insert(
            calendarId=calendar_id,
            body=event_body,
        ).execute()

    def update_event(
        self,
        calendar_id: str,
        event_id: str,
        title: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        description: Optional[str] = None,
        color_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Update an existing calendar event.

        Args:
            calendar_id: Calendar ID
            event_id: Event ID to update
            title: New title (optional)
            start_time: New start time (optional)
            end_time: New end time (optional)
            description: New description (optional)
            color_id: New color ID (optional)

        Returns:
            Updated event dict
        """
        # Get existing event
        event = self.service.events().get(
            calendarId=calendar_id,
            eventId=event_id,
        ).execute()

        # Update fields
        if title:
            event["summary"] = title

        if start_time:
            event["start"] = {
                "dateTime": start_time.isoformat(),
                "timeZone": self._get_timezone(),
            }

        if end_time:
            event["end"] = {
                "dateTime": end_time.isoformat(),
                "timeZone": self._get_timezone(),
            }

        if description is not None:
            event["description"] = description

        if color_id:
            event["colorId"] = str(color_id)

        return self.service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=event,
        ).execute()

    def delete_event(self, calendar_id: str, event_id: str) -> bool:
        """
        Delete a calendar event.

        Args:
            calendar_id: Calendar ID
            event_id: Event ID to delete

        Returns:
            True if deleted successfully
        """
        try:
            self.service.events().delete(
                calendarId=calendar_id,
                eventId=event_id,
            ).execute()
            return True
        except Exception:
            return False

    def get_event(
        self,
        calendar_id: str,
        event_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific event by ID.

        Args:
            calendar_id: Calendar ID
            event_id: Event ID

        Returns:
            Event dict or None if not found
        """
        try:
            return self.service.events().get(
                calendarId=calendar_id,
                eventId=event_id,
            ).execute()
        except Exception:
            return None

    def find_events(
        self,
        calendar_id: str,
        query: Optional[str] = None,
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find events in a calendar.

        Args:
            calendar_id: Calendar ID
            query: Search query
            time_min: Minimum start time
            time_max: Maximum start time

        Returns:
            List of matching events
        """
        params = {"calendarId": calendar_id, "singleEvents": True}

        if query:
            params["q"] = query

        if time_min:
            params["timeMin"] = time_min.isoformat() + "Z"

        if time_max:
            params["timeMax"] = time_max.isoformat() + "Z"

        events = []
        page_token = None

        while True:
            if page_token:
                params["pageToken"] = page_token

            result = self.service.events().list(**params).execute()
            events.extend(result.get("items", []))
            page_token = result.get("nextPageToken")

            if not page_token:
                break

        return events

    def get_color_for_course(self, course_name: str) -> int:
        """
        Get a consistent color ID for a course.

        Args:
            course_name: Course name

        Returns:
            Google Calendar color ID (1-11)
        """
        if course_name not in self._course_colors:
            # Assign next color in rotation
            color_index = len(self._course_colors) % len(COURSE_COLOR_ROTATION)
            self._course_colors[course_name] = COURSE_COLOR_ROTATION[color_index]

        return self._course_colors[course_name]

    def get_color_for_urgency(self, due_date: datetime) -> int:
        """
        Get color ID based on due date urgency.

        Args:
            due_date: Assignment due date

        Returns:
            Google Calendar color ID (1-11)
        """
        now = datetime.now()
        days_until = (due_date - now).days

        if days_until < 0:
            return URGENCY_COLORS["overdue"]
        elif days_until == 0:
            return URGENCY_COLORS["today"]
        elif days_until == 1:
            return URGENCY_COLORS["tomorrow"]
        elif days_until <= 7:
            return URGENCY_COLORS["this_week"]
        else:
            return URGENCY_COLORS["later"]

    def _get_timezone(self) -> str:
        """Get the user's timezone from primary calendar."""
        try:
            primary = self.service.calendars().get(calendarId="primary").execute()
            return primary.get("timeZone", "America/New_York")
        except Exception:
            return "America/New_York"

    @staticmethod
    def generate_event_id(canvas_assignment_id: int, student_id: int) -> str:
        """
        Generate a unique event ID for a Canvas assignment.

        Args:
            canvas_assignment_id: Canvas assignment ID
            student_id: Canvas student ID

        Returns:
            Event ID string (must be lowercase alphanumeric + hyphens)
        """
        # Google Calendar event IDs must be 5-1024 chars, lowercase a-v and 0-9
        return f"canvas{student_id}a{canvas_assignment_id}"


class AssignmentSync:
    """
    Syncs Canvas assignments to Google Calendar.

    Handles create, update, and delete operations to keep
    calendar in sync with Canvas.
    """

    def __init__(
        self,
        calendar_service: Optional[CalendarService] = None,
        color_by: str = "course",
    ):
        """
        Initialize assignment sync.

        Args:
            calendar_service: CalendarService instance
            color_by: Color coding method - 'course' or 'urgency'
        """
        self.calendar = calendar_service or CalendarService()
        self.color_by = color_by

    def sync_assignments(
        self,
        student_id: int,
        student_name: str,
        assignments: List[Dict[str, Any]],
        calendar_id: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        Sync assignments to a student's calendar.

        Args:
            student_id: Canvas student ID
            student_name: Student's display name
            assignments: List of assignment dicts from Canvas API
            calendar_id: Optional specific calendar ID

        Returns:
            Dict with counts: {'created': n, 'updated': n, 'deleted': n, 'skipped': n}
        """
        # Get or create calendar
        cal = self.calendar.get_student_calendar(student_name, calendar_id)
        cal_id = cal["id"]

        stats = {"created": 0, "updated": 0, "deleted": 0, "skipped": 0}

        # Track synced event IDs
        synced_ids = set()

        for assignment in assignments:
            due_at = assignment.get("due_at")
            if not due_at:
                stats["skipped"] += 1
                continue

            try:
                due_date = datetime.strptime(due_at, "%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                stats["skipped"] += 1
                continue

            # Generate event ID
            canvas_id = assignment.get("id") or assignment.get("canvas_id")
            if not canvas_id:
                stats["skipped"] += 1
                continue

            event_id = self.calendar.generate_event_id(canvas_id, student_id)
            synced_ids.add(event_id)

            # Prepare event data
            course_name = assignment.get("course_name", "Unknown Course")
            assignment_name = assignment.get("name", "Unknown Assignment")
            points = assignment.get("points_possible", 0)

            title = f"📚 {assignment_name}"
            description = (
                f"Course: {course_name}\n"
                f"Points: {points}\n"
                f"Due: {due_date.strftime('%B %d, %Y at %I:%M %p')}\n\n"
                f"Canvas Assignment ID: {canvas_id}"
            )

            # Get color
            if self.color_by == "urgency":
                color_id = self.calendar.get_color_for_urgency(due_date)
            else:
                color_id = self.calendar.get_color_for_course(course_name)

            # Check if event exists
            existing = self.calendar.get_event(cal_id, event_id)

            if existing:
                # Update existing event
                self.calendar.update_event(
                    calendar_id=cal_id,
                    event_id=event_id,
                    title=title,
                    start_time=due_date,
                    end_time=due_date + timedelta(hours=1),
                    description=description,
                    color_id=color_id,
                )
                stats["updated"] += 1
            else:
                # Create new event
                try:
                    self.calendar.create_event(
                        calendar_id=cal_id,
                        title=title,
                        start_time=due_date,
                        end_time=due_date + timedelta(hours=1),
                        description=description,
                        color_id=color_id,
                        event_id=event_id,
                    )
                    stats["created"] += 1
                except Exception as e:
                    # Event might already exist with different ID
                    stats["skipped"] += 1

        return stats

    def cleanup_old_events(
        self,
        calendar_id: str,
        days_old: int = 30,
    ) -> int:
        """
        Remove events for past assignments.

        Args:
            calendar_id: Calendar ID
            days_old: Delete events older than this many days

        Returns:
            Number of events deleted
        """
        cutoff = datetime.now() - timedelta(days=days_old)
        old_events = self.calendar.find_events(
            calendar_id=calendar_id,
            time_max=cutoff,
        )

        deleted = 0
        for event in old_events:
            # Only delete Canvas-created events
            if event.get("id", "").startswith("canvas"):
                if self.calendar.delete_event(calendar_id, event["id"]):
                    deleted += 1

        return deleted


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    print("Google Calendar Service Test")
    print("=" * 50)

    try:
        calendar = CalendarService()

        # List calendars
        calendars = calendar.list_calendars()
        print(f"\nFound {len(calendars)} calendars:")
        for cal in calendars[:5]:
            print(f"  - {cal.get('summary')} ({cal.get('id')[:30]}...)")

        if len(calendars) > 5:
            print(f"  ... and {len(calendars) - 5} more")

        # Show timezone
        tz = calendar._get_timezone()
        print(f"\nTimezone: {tz}")

    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure you have authenticated with Google first:")
        print("  python google_services/auth.py")
