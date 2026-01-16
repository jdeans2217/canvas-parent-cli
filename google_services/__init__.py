"""
Google Workspace integrations for Canvas Parent CLI.

Provides authentication and services for:
- Gmail (email reports)
- Calendar (due date sync)
- Docs (study materials)
- Drive (document storage)
"""

from google_services.auth import GoogleAuth, get_authenticated_service
from google_services.gmail_service import GmailService
from google_services.calendar_service import CalendarService, AssignmentSync
from google_services.drive_service import DriveService

__all__ = [
    "GoogleAuth",
    "get_authenticated_service",
    "GmailService",
    "CalendarService",
    "AssignmentSync",
    "DriveService",
]
