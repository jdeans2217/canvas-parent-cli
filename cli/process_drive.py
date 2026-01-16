#!/usr/bin/env python3
"""
Process Drive CLI - Process scanned documents from Google Drive.

Commands:
    python -m cli.process_drive scan                      Process shared folder with smart detection
    python -m cli.process_drive scan --student NAME       Process student-specific folder
    python -m cli.process_drive list                      List unprocessed files
    python -m cli.process_drive pending                   Show pending documents needing assignment
    python -m cli.process_drive daemon                    Run background processor
    python -m cli.process_drive status                    Show configuration status
"""

import argparse
import logging
import sys
import time
from datetime import datetime

from config import get_config
from database.connection import get_session
from database.models import Student

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_student_folder_config():
    """Get student -> folder_id mapping from config."""
    config = get_config()
    return config.drive.student_folders


def get_student(session, student_arg: str = None) -> Student:
    """Get student from database by name or ID."""
    if student_arg:
        # Try by ID first
        if student_arg.isdigit():
            student = session.query(Student).filter_by(id=int(student_arg)).first()
            if student:
                return student

        # Try by name (partial match)
        student = session.query(Student).filter(
            Student.name.ilike(f"%{student_arg}%")
        ).first()
        if student:
            return student

    # Return first student if none specified
    return session.query(Student).first()


def find_folder_for_student(student: Student, folder_map: dict) -> str:
    """Find the Drive folder ID for a student."""
    # Try to match student name to folder config
    for key, folder_id in folder_map.items():
        # Match by first name or full key
        if key.lower() in student.name.lower():
            return folder_id
        # Also try matching the folder key against first name
        first_name = student.name.split()[0].lower()
        if first_name in key.lower():
            return folder_id
    return None


def cmd_scan(args):
    """Process new files from Drive."""
    from scanner.drive_processor import DriveProcessor
    from scanner.notifications import send_assignment_notification

    config = get_config()
    session = get_session()
    processor = DriveProcessor(session=session)

    # Determine mode: shared folder or student-specific
    if args.student:
        # Student-specific mode
        student = get_student(session, args.student)
        if not student:
            print("Error: No student found. Use --student to specify.")
            sys.exit(1)

        folder_map = get_student_folder_config()
        folder_id = find_folder_for_student(student, folder_map)

        if not folder_id:
            print(f"Error: No Drive folder configured for {student.name}")
            first_name = student.name.split()[0].upper()
            print(f"Set DRIVE_{first_name}_FOLDER_ID in .env")
            sys.exit(1)

        print(f"Processing Drive folder for: {student.name}")
        print("=" * 60)

        results = processor.process_folder(
            folder_id=folder_id,
            student_id=student.id,
            move_to_processed=config.drive.move_to_processed,
        )
    else:
        # Shared folder mode with smart detection
        folder_id = config.drive.shared_folder_id

        if not folder_id:
            # Fall back to first student folder if no shared folder
            folder_map = get_student_folder_config()
            if folder_map:
                folder_id = list(folder_map.values())[0]
                print("Note: Using first student folder (no shared folder configured)")
            else:
                print("Error: No Drive folder configured")
                print("Set DRIVE_SHARED_FOLDER_ID or DRIVE_<NAME>_FOLDER_ID in .env")
                sys.exit(1)

        print("Processing shared Drive folder with smart detection")
        print("=" * 60)

        results = processor.process_shared_folder(
            folder_id=folder_id,
            confidence_threshold=config.drive.confidence_threshold,
            move_files=config.drive.move_to_processed,
        )

    # Report results
    if not results:
        print("\nNo new files to process.")
        return

    success_count = sum(1 for r in results if r.success)
    processed_count = sum(1 for r in results if r.status == "processed")
    pending_count = sum(1 for r in results if r.status == "pending")
    duplicate_count = sum(1 for r in results if r.status == "duplicate")

    print(f"\nProcessed {len(results)} files:")
    print(f"  Successful: {success_count}")
    print(f"  Auto-assigned: {processed_count}")
    print(f"  Pending review: {pending_count}")
    if duplicate_count:
        print(f"  Duplicates skipped: {duplicate_count}")

    for result in results:
        print(f"\n  {result.drive_file.name}:")
        if result.success:
            # Show detection info
            if result.student_detection:
                det = result.student_detection
                if det.student:
                    print(f"    Student: {det.student.name} ({det.confidence:.0f}% - {det.method})")
                else:
                    print(f"    Student: Unknown ({det.method})")
                if det.reasons:
                    for reason in det.reasons[:2]:
                        print(f"      → {reason}")

            # Show parsed info
            if result.parsed and result.parsed.title:
                print(f"    Title: {result.parsed.title}")
            if result.parsed and result.parsed.score:
                print(f"    Score: {result.parsed.score.earned}/{result.parsed.score.possible}")

            # Show assignment match
            if result.match and result.match.assignment:
                print(f"    Matched: {result.match.assignment.name} ({result.match.confidence:.0f}%)")

            # Show status
            if result.status == "pending":
                print(f"    Status: PENDING - needs manual assignment")
                # Send notification if configured
                if config.drive.notification_email and result.document_id:
                    from database.models import ScannedDocument
                    doc = session.query(ScannedDocument).filter_by(id=result.document_id).first()
                    if doc:
                        if send_assignment_notification(doc):
                            print(f"    Notification sent to: {config.drive.notification_email}")
            elif result.status == "duplicate":
                print(f"    Status: DUPLICATE - {result.error}")
            else:
                print(f"    Status: Processed")
        else:
            print(f"    Error: {result.error}")


def cmd_list(args):
    """List unprocessed files in Drive."""
    from scanner.drive_processor import DriveProcessor

    config = get_config()
    session = get_session()

    # Determine which folder to list
    if args.student:
        student = get_student(session, args.student)
        if not student:
            print("Error: No student found.")
            sys.exit(1)

        folder_map = get_student_folder_config()
        folder_id = find_folder_for_student(student, folder_map)
        folder_name = f"{student.name}'s folder"
    else:
        folder_id = config.drive.shared_folder_id
        folder_name = "shared folder"

        if not folder_id:
            folder_map = get_student_folder_config()
            if folder_map:
                folder_id = list(folder_map.values())[0]
                folder_name = "first configured folder"

    if not folder_id:
        print("Error: No Drive folder configured")
        sys.exit(1)

    print(f"Unprocessed files in {folder_name}")
    print("=" * 60)

    processor = DriveProcessor(session=session)
    new_files = processor.get_new_files(folder_id)

    if not new_files:
        print("\nNo new files to process.")
        return

    print(f"\nFound {len(new_files)} unprocessed files:\n")
    for f in new_files:
        print(f"  {f.name}")
        print(f"    Type: {f.mime_type}")
        print(f"    Size: {f.size / 1024:.1f} KB")
        print(f"    Created: {f.created_time.strftime('%Y-%m-%d %H:%M')}")
        print()


def cmd_pending(args):
    """Show documents pending manual assignment."""
    from database.models import ScannedDocument

    session = get_session()

    # Find documents without student assignment
    pending_docs = session.query(ScannedDocument).filter(
        ScannedDocument.student_id.is_(None)
    ).order_by(ScannedDocument.scan_date.desc()).all()

    print("Documents Pending Assignment")
    print("=" * 60)

    if not pending_docs:
        print("\nNo pending documents.")
        return

    print(f"\nFound {len(pending_docs)} pending documents:\n")

    students = session.query(Student).all()
    student_names = ", ".join(s.name for s in students)

    for doc in pending_docs:
        print(f"  ID: {doc.id}")
        print(f"  File: {doc.file_name}")
        print(f"  Scanned: {doc.scan_date.strftime('%Y-%m-%d %H:%M') if doc.scan_date else 'Unknown'}")
        if doc.detected_title:
            print(f"  Title: {doc.detected_title}")
        if doc.detected_score:
            print(f"  Score: {doc.detected_score}/{doc.detected_max_score or '?'}")
        print(f"  Assign with: python -m cli.assign_document {doc.id} --student <{student_names}>")
        print()


def cmd_daemon(args):
    """Run background processor."""
    from scanner.drive_processor import DriveProcessor
    from scanner.notifications import send_assignment_notification

    config = get_config()
    interval = args.interval or config.drive.polling_interval

    print("Starting Drive scan daemon")
    print(f"Polling interval: {interval} seconds")
    print(f"Confidence threshold: {config.drive.confidence_threshold}%")
    print("Press Ctrl+C to stop\n")

    # Determine mode
    shared_folder = config.drive.shared_folder_id
    folder_map = get_student_folder_config()

    session = get_session()
    processor = DriveProcessor(session=session)

    if shared_folder:
        print(f"Mode: Shared folder with smart detection")
        print(f"Folder: {shared_folder[:20]}...")
    elif folder_map:
        print(f"Mode: Per-student folders")
        students = session.query(Student).all()
        student_folders = []
        for student in students:
            folder_id = find_folder_for_student(student, folder_map)
            if folder_id:
                student_folders.append((student, folder_id))
                print(f"  Monitoring: {student.name}")
    else:
        print("Error: No Drive folders configured")
        sys.exit(1)

    print()

    try:
        while True:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if shared_folder:
                # Process shared folder
                try:
                    new_files = processor.get_new_files(shared_folder)
                    if new_files:
                        print(f"[{timestamp}] Found {len(new_files)} new files")
                        results = processor.process_shared_folder(
                            folder_id=shared_folder,
                            confidence_threshold=config.drive.confidence_threshold,
                            move_files=config.drive.move_to_processed,
                        )

                        processed = sum(1 for r in results if r.status == "processed")
                        pending = sum(1 for r in results if r.status == "pending")
                        print(f"[{timestamp}] Processed: {processed}, Pending: {pending}")

                        # Send notifications for pending
                        if config.drive.notification_email:
                            from database.models import ScannedDocument
                            for r in results:
                                if r.status == "pending" and r.document_id:
                                    doc = session.query(ScannedDocument).filter_by(id=r.document_id).first()
                                    if doc:
                                        send_assignment_notification(doc)
                except Exception as e:
                    logger.error(f"Error processing shared folder: {e}")
            else:
                # Process per-student folders
                for student, folder_id in student_folders:
                    try:
                        new_files = processor.get_new_files(folder_id)
                        if new_files:
                            print(f"[{timestamp}] Found {len(new_files)} new files for {student.name}")
                            results = processor.process_folder(
                                folder_id=folder_id,
                                student_id=student.id,
                                move_to_processed=config.drive.move_to_processed,
                            )
                            success = sum(1 for r in results if r.success)
                            print(f"[{timestamp}] Processed {success}/{len(results)} files")
                    except Exception as e:
                        logger.error(f"Error processing {student.name}: {e}")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\nDaemon stopped")


def cmd_status(args):
    """Show configuration status."""
    config = get_config()

    print("Drive Scanning Configuration")
    print("=" * 60)

    print(f"\nEnabled: {config.drive.enabled}")
    print(f"Polling Interval: {config.drive.polling_interval}s")
    print(f"Move to Processed: {config.drive.move_to_processed}")
    print(f"Confidence Threshold: {config.drive.confidence_threshold}%")

    # Shared folder
    if config.drive.shared_folder_id:
        shared_id = config.drive.shared_folder_id
        print(f"\nShared Folder: {shared_id[:30]}..." if len(shared_id) > 30 else f"\nShared Folder: {shared_id}")
        print("  Mode: Smart student detection")
    else:
        print("\nShared Folder: Not configured")

    # Per-student folders
    print("\nStudent Folders:")
    folder_map = config.drive.student_folders
    if not folder_map:
        print("  None configured")
    else:
        for name, folder_id in folder_map.items():
            display_id = f"{folder_id[:20]}..." if len(folder_id) > 20 else folder_id
            print(f"  {name}: {display_id}")

    # Notification settings
    print("\nNotifications:")
    if config.drive.notification_email:
        print(f"  Email: {config.drive.notification_email}")
        print(f"  Assignment URL: {config.drive.assign_base_url}")
    else:
        print("  Not configured (set NOTIFICATION_EMAIL in .env)")

    # Check Google auth
    print("\nGoogle Drive Authentication:")
    try:
        from google_services.drive_service import DriveService
        drive = DriveService()
        about = drive.service.about().get(fields="user").execute()
        print(f"  Status: Authenticated as {about['user']['emailAddress']}")
    except Exception as e:
        print(f"  Status: Not authenticated")
        print(f"  Error: {e}")
        print("  Run: python google_services/setup_google_auth.py")


def cmd_history(args):
    """Show history of processed documents."""
    from database.models import ScannedDocument, Assignment

    session = get_session()

    # Build query
    query = session.query(ScannedDocument).order_by(ScannedDocument.scan_date.desc())

    # Filter by student if specified
    if args.student:
        student = get_student(session, args.student)
        if student:
            query = query.filter(ScannedDocument.student_id == student.id)
            print(f"Scan History for {student.name}")
        else:
            print(f"Student '{args.student}' not found")
            return
    else:
        print("Scan History (All Students)")

    # Filter by status if specified
    if args.status:
        query = query.filter(ScannedDocument.status == args.status)

    # Limit results
    limit = args.limit or 20
    docs = query.limit(limit).all()

    print("=" * 70)

    if not docs:
        print("\nNo documents found.")
        return

    print(f"\nShowing {len(docs)} document(s):\n")

    students = {s.id: s for s in session.query(Student).all()}

    for doc in docs:
        student = students.get(doc.student_id)
        status_icon = {"processed": "✓", "pending": "⏳", "failed": "✗", "duplicate": "⊜"}.get(doc.status or "processed", "?")

        print(f"[{doc.id}] {status_icon} {doc.file_name}")
        print(f"    Student: {student.name if student else 'Unassigned'}")
        print(f"    Status: {doc.status or 'processed'}")
        print(f"    Scanned: {doc.scan_date.strftime('%Y-%m-%d %H:%M') if doc.scan_date else 'Unknown'}")

        if doc.detection_method:
            print(f"    Detection: {doc.detection_method} ({doc.detection_confidence:.0f}%)" if doc.detection_confidence else f"    Detection: {doc.detection_method}")

        if doc.detected_title:
            print(f"    Title: {doc.detected_title}")

        if doc.detected_score is not None:
            score_str = f"{doc.detected_score}"
            if doc.detected_max_score:
                score_str += f"/{doc.detected_max_score}"
            print(f"    Score: {score_str}")

        if doc.assignment_id:
            assignment = session.query(Assignment).filter_by(id=doc.assignment_id).first()
            if assignment:
                print(f"    Matched: {assignment.name}")

        if doc.ocr_text and args.verbose:
            preview = doc.ocr_text[:200].replace("\n", " ")
            if len(doc.ocr_text) > 200:
                preview += "..."
            print(f"    OCR Preview: {preview}")

        print()

    if len(docs) == limit:
        print(f"(Showing first {limit} results. Use --limit to see more)")


def main():
    parser = argparse.ArgumentParser(
        description="Process scanned documents from Google Drive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Process shared folder with smart detection:
    python -m cli.process_drive scan

  Process specific student's folder:
    python -m cli.process_drive scan --student JJ

  Show pending documents:
    python -m cli.process_drive pending

  View scan history:
    python -m cli.process_drive history

  Run background daemon:
    python -m cli.process_drive daemon
"""
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Process new files")
    scan_parser.add_argument("-s", "--student", help="Student name or ID (omit for shared folder)")
    scan_parser.set_defaults(func=cmd_scan)

    # List command
    list_parser = subparsers.add_parser("list", help="List unprocessed files")
    list_parser.add_argument("-s", "--student", help="Student name or ID")
    list_parser.set_defaults(func=cmd_list)

    # Pending command
    pending_parser = subparsers.add_parser("pending", help="Show pending documents")
    pending_parser.set_defaults(func=cmd_pending)

    # Daemon command
    daemon_parser = subparsers.add_parser("daemon", help="Run background processor")
    daemon_parser.add_argument(
        "-i", "--interval",
        type=int,
        help="Polling interval in seconds"
    )
    daemon_parser.set_defaults(func=cmd_daemon)

    # Status command
    status_parser = subparsers.add_parser("status", help="Show config status")
    status_parser.set_defaults(func=cmd_status)

    # History command
    history_parser = subparsers.add_parser("history", help="Show scan history")
    history_parser.add_argument("-s", "--student", help="Filter by student name or ID")
    history_parser.add_argument("--status", choices=["processed", "pending", "failed", "duplicate"], help="Filter by status")
    history_parser.add_argument("-n", "--limit", type=int, default=20, help="Number of results (default: 20)")
    history_parser.add_argument("-v", "--verbose", action="store_true", help="Show OCR text preview")
    history_parser.set_defaults(func=cmd_history)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
