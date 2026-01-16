#!/usr/bin/env python3
"""
Process Dropbox CLI - Process scanned documents from Dropbox.

Commands:
    python -m cli.process_dropbox scan          Process scan folder with smart detection
    python -m cli.process_dropbox list          List unprocessed files
    python -m cli.process_dropbox pending       Show pending documents needing assignment
    python -m cli.process_dropbox daemon        Run background processor
    python -m cli.process_dropbox status        Show configuration status
    python -m cli.process_dropbox auth          Run Dropbox authentication
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


def cmd_auth(args):
    """Run Dropbox authentication flow."""
    from cloud_services.dropbox_auth import DropboxAuth

    config = get_config()

    if not config.dropbox.app_key:
        print("Error: Dropbox app key not configured")
        print("Set DROPBOX_APP_KEY and DROPBOX_APP_SECRET in .env")
        sys.exit(1)

    print("Dropbox Authentication")
    print("=" * 60)

    auth = DropboxAuth()

    if auth.is_authenticated():
        email = auth.get_user_email()
        print(f"\nAlready authenticated as: {email}")
        print("To re-authenticate, delete dropbox_token.json and run again.")
    else:
        # Running auth flow will prompt user
        if auth.client:
            email = auth.get_user_email()
            print(f"\nAuthentication successful!")
            print(f"Authenticated as: {email}")
        else:
            print("\nAuthentication failed.")
            sys.exit(1)


def cmd_scan(args):
    """Process new files from Dropbox."""
    from scanner.dropbox_processor import DropboxProcessor
    from scanner.notifications import send_assignment_notification

    config = get_config()
    session = get_session()

    if not config.dropbox.is_valid():
        print("Error: Dropbox not configured")
        print("Set DROPBOX_APP_KEY and DROPBOX_APP_SECRET in .env")
        sys.exit(1)

    processor = DropboxProcessor(session=session)

    # Get scan folder from config or argument
    folder_path = args.folder or config.dropbox.scan_folder

    print(f"Processing Dropbox folder: {folder_path or '(app folder root)'}")
    print("=" * 60)

    results = processor.process_folder(
        folder_path=folder_path,
        confidence_threshold=config.dropbox.confidence_threshold,
        move_files=config.dropbox.move_to_processed,
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
        print(f"\n  {result.dropbox_file.name}:")
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
                        print(f"      -> {reason}")

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
    """List unprocessed files in Dropbox."""
    from scanner.dropbox_processor import DropboxProcessor

    config = get_config()
    session = get_session()

    if not config.dropbox.is_valid():
        print("Error: Dropbox not configured")
        sys.exit(1)

    folder_path = args.folder or config.dropbox.scan_folder

    print(f"Unprocessed files in: {folder_path or '(app folder root)'}")
    print("=" * 60)

    processor = DropboxProcessor(session=session)
    new_files = processor.get_new_files(folder_path)

    if not new_files:
        print("\nNo new files to process.")
        return

    print(f"\nFound {len(new_files)} unprocessed files:\n")
    for f in new_files:
        print(f"  {f.name}")
        print(f"    Type: {f.mime_type}")
        print(f"    Size: {f.size / 1024:.1f} KB")
        print(f"    Path: {f.file_path}")
        print()


def cmd_pending(args):
    """Show documents pending manual assignment."""
    from database.models import ScannedDocument

    session = get_session()

    # Find Dropbox documents without student assignment
    pending_docs = session.query(ScannedDocument).filter(
        ScannedDocument.source == "dropbox",
        ScannedDocument.student_id.is_(None)
    ).order_by(ScannedDocument.scan_date.desc()).all()

    print("Dropbox Documents Pending Assignment")
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
    from scanner.dropbox_processor import DropboxProcessor
    from scanner.notifications import send_assignment_notification

    config = get_config()

    if not config.dropbox.is_valid():
        print("Error: Dropbox not configured")
        sys.exit(1)

    interval = args.interval or config.dropbox.polling_interval

    print("Starting Dropbox scan daemon")
    print(f"Polling interval: {interval} seconds")
    print(f"Confidence threshold: {config.dropbox.confidence_threshold}%")
    print(f"Scan folder: {config.dropbox.scan_folder or '(root)'}")
    print("Press Ctrl+C to stop\n")

    session = get_session()
    processor = DropboxProcessor(session=session)

    try:
        while True:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            try:
                new_files = processor.get_new_files(config.dropbox.scan_folder)
                if new_files:
                    print(f"[{timestamp}] Found {len(new_files)} new files")
                    results = processor.process_folder(
                        folder_path=config.dropbox.scan_folder,
                        confidence_threshold=config.dropbox.confidence_threshold,
                        move_files=config.dropbox.move_to_processed,
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
                logger.error(f"Error processing folder: {e}")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\nDaemon stopped")


def cmd_status(args):
    """Show configuration status."""
    config = get_config()

    print("Dropbox Configuration")
    print("=" * 60)

    print(f"\nEnabled: {config.dropbox.enabled}")
    if config.dropbox.app_key:
        print(f"App Key: {config.dropbox.app_key[:8]}...")
    else:
        print(f"App Key: NOT SET")
    print(f"Polling Interval: {config.dropbox.polling_interval}s")
    print(f"Move to Processed: {config.dropbox.move_to_processed}")
    print(f"Confidence Threshold: {config.dropbox.confidence_threshold}%")

    if config.dropbox.scan_folder:
        print(f"\nScan Folder: {config.dropbox.scan_folder}")
    else:
        print(f"\nScan Folder: (app folder root)")

    # Per-student folders
    print("\nStudent Folders:")
    if not config.dropbox.student_folders:
        print("  None configured (will auto-create)")
    else:
        for name, path in config.dropbox.student_folders.items():
            print(f"  {name}: {path}")

    # Check Dropbox auth
    print("\nDropbox Authentication:")
    if not config.dropbox.is_valid():
        print("  Status: Not configured")
        print("  Set DROPBOX_APP_KEY and DROPBOX_APP_SECRET in .env")
    else:
        try:
            from cloud_services.dropbox_service import DropboxService
            service = DropboxService()
            account = service.client.users_get_current_account()
            print(f"  Status: Authenticated as {account.email}")

            # List root files
            files = service.list_files("")
            print(f"  Files in app folder: {len(files)}")
        except Exception as e:
            print(f"  Status: Not authenticated")
            print(f"  Error: {e}")
            print("  Run: python -m cli.process_dropbox auth")


def cmd_history(args):
    """Show history of processed documents from Dropbox."""
    from database.models import ScannedDocument, Assignment

    session = get_session()

    # Build query
    query = session.query(ScannedDocument).filter(
        ScannedDocument.source == "dropbox"
    ).order_by(ScannedDocument.scan_date.desc())

    # Filter by student if specified
    if args.student:
        student = get_student(session, args.student)
        if student:
            query = query.filter(ScannedDocument.student_id == student.id)
            print(f"Dropbox Scan History for {student.name}")
        else:
            print(f"Student '{args.student}' not found")
            return
    else:
        print("Dropbox Scan History (All Students)")

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
        status_icon = {"processed": "OK", "pending": "??", "failed": "XX", "duplicate": "=="}.get(doc.status or "processed", "?")

        print(f"[{doc.id}] {status_icon} {doc.file_name}")
        print(f"    Student: {student.name if student else 'Unassigned'}")
        print(f"    Status: {doc.status or 'processed'}")
        print(f"    Scanned: {doc.scan_date.strftime('%Y-%m-%d %H:%M') if doc.scan_date else 'Unknown'}")

        if doc.detection_method:
            conf_str = f" ({doc.detection_confidence:.0f}%)" if doc.detection_confidence else ""
            print(f"    Detection: {doc.detection_method}{conf_str}")

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

        if doc.dropbox_path:
            print(f"    Path: {doc.dropbox_path}")

        print()

    if len(docs) == limit:
        print(f"(Showing first {limit} results. Use --limit to see more)")


def main():
    parser = argparse.ArgumentParser(
        description="Process scanned documents from Dropbox",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Authenticate with Dropbox:
    python -m cli.process_dropbox auth

  Process scan folder:
    python -m cli.process_dropbox scan

  Show pending documents:
    python -m cli.process_dropbox pending

  View scan history:
    python -m cli.process_dropbox history

  Run background daemon:
    python -m cli.process_dropbox daemon
"""
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Auth command
    auth_parser = subparsers.add_parser("auth", help="Run Dropbox authentication")
    auth_parser.set_defaults(func=cmd_auth)

    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Process new files")
    scan_parser.add_argument("-f", "--folder", help="Folder path (default: from config)")
    scan_parser.set_defaults(func=cmd_scan)

    # List command
    list_parser = subparsers.add_parser("list", help="List unprocessed files")
    list_parser.add_argument("-f", "--folder", help="Folder path")
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
    history_parser.set_defaults(func=cmd_history)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
