#!/usr/bin/env python3
"""
Process Scan CLI - Process scanned homework images.

Commands:
    python -m cli.process_scan file <path>      Process a single file
    python -m cli.process_scan email            Process homework from email
    python -m cli.process_scan inbox            Monitor inbox for new emails
"""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime

from config import get_config
from database.connection import get_session
from database.models import Student

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def process_file(args):
    """Process a single image or PDF file."""
    from scanner.ocr import MistralOCR
    from scanner.parser import GradeParser

    file_path = Path(args.file)

    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    print(f"Processing: {file_path}")
    print("=" * 60)

    # Initialize OCR
    try:
        ocr = MistralOCR()
    except ValueError as e:
        print(f"Error: {e}")
        print("\nSet MISTRAL_API_KEY in your .env file")
        sys.exit(1)

    # Run OCR
    result = ocr.process_file(str(file_path))

    if not result.success:
        print(f"OCR failed: {result.error}")
        sys.exit(1)

    print(f"\nOCR completed in {result.processing_time:.2f}s")
    print(f"Pages: {result.total_pages}")
    print(f"File size: {result.file_size_kb:.1f} KB")

    # Parse extracted text
    parser = GradeParser()
    parsed = parser.parse(result.full_text)

    print("\n" + "=" * 60)
    print("EXTRACTED INFORMATION:")
    print("=" * 60)

    if parsed.title:
        print(f"Title: {parsed.title} (confidence: {parsed.title_confidence:.0f}%)")

    if parsed.date:
        print(f"Date: {parsed.date.strftime('%Y-%m-%d')} (confidence: {parsed.date_confidence:.0f}%)")

    if parsed.score:
        print(f"Score: {parsed.score.earned}/{parsed.score.possible} = {parsed.score.percentage}%")
        if parsed.score.letter_grade:
            print(f"Letter Grade: {parsed.score.letter_grade}")
        print(f"  (confidence: {parsed.score_confidence:.0f}%)")

    if parsed.student_name:
        print(f"Student: {parsed.student_name}")

    if parsed.course_name:
        print(f"Course: {parsed.course_name}")

    # Show raw text if verbose
    if args.verbose:
        print("\n" + "=" * 60)
        print("RAW OCR TEXT:")
        print("=" * 60)
        print(result.full_text)

    # Match to assignment if requested
    if args.match:
        print("\n" + "=" * 60)
        print("ASSIGNMENT MATCHING:")
        print("=" * 60)

        try:
            session = get_session()
            student = get_student(session, args.student)

            if student:
                from scanner.matcher import AssignmentMatcher

                matcher = AssignmentMatcher(session)
                matches = matcher.find_matches(parsed, student.id, limit=3)

                if matches:
                    print(f"\nTop matches for {student.name}:")
                    for i, match in enumerate(matches, 1):
                        if match.assignment:
                            print(f"\n  {i}. {match.assignment.name}")
                            print(f"     Course: {match.assignment.course.name}")
                            print(f"     Due: {match.assignment.due_at}")
                            print(f"     Confidence: {match.confidence:.1f}%")
                            print(f"     Method: {match.method}")
                else:
                    print("\nNo matching assignments found")
            else:
                print("No student found. Use --student to specify.")

        except Exception as e:
            print(f"Matching failed: {e}")

    # Save output if requested
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            f.write(f"# OCR Results for {file_path.name}\n")
            f.write(f"Processed: {datetime.now().isoformat()}\n\n")
            f.write(result.full_markdown)

        print(f"\nOutput saved to: {output_path}")


def process_email(args):
    """Process homework photos from email attachments."""
    from scanner.email_processor import EmailProcessor

    print("Processing homework emails...")
    print("=" * 60)

    try:
        session = get_session()
        student = get_student(session, args.student)

        if not student:
            print("Error: No student found. Use --student to specify.")
            sys.exit(1)

        print(f"Student: {student.name}")

        processor = EmailProcessor(session=session)

        # Get unread emails
        if args.list_only:
            messages = processor.get_unread_with_attachments(
                query=args.query or "",
                max_results=args.max,
            )

            print(f"\nFound {len(messages)} unread emails with attachments:")

            for msg in messages:
                attachments = processor.get_attachments(msg["id"])
                if attachments:
                    att = attachments[0]
                    print(f"\n  From: {att.sender}")
                    print(f"  Subject: {att.subject}")
                    print(f"  Date: {att.received_date}")
                    print(f"  Attachments: {len(attachments)}")
                    for a in attachments:
                        print(f"    - {a.filename} ({a.size} bytes)")

            return

        # Process emails
        results = processor.process_inbox(
            student_id=student.id,
            query=args.query or "",
            max_emails=args.max,
            save_to_disk=args.output,
            mark_processed=not args.no_mark,
        )

        # Report results
        print(f"\nProcessed {len(results)} attachments:")

        success_count = sum(1 for r in results if r.success)
        matched_count = sum(1 for r in results if r.success and r.match and r.match.assignment)

        print(f"  Successful: {success_count}")
        print(f"  Matched to assignments: {matched_count}")

        for result in results:
            print(f"\n  {result.attachment.filename}:")
            if result.success:
                if result.parsed and result.parsed.title:
                    print(f"    Title: {result.parsed.title}")
                if result.parsed and result.parsed.score:
                    print(f"    Score: {result.parsed.score.earned}/{result.parsed.score.possible}")
                if result.match and result.match.assignment:
                    print(f"    Matched: {result.match.assignment.name} ({result.match.confidence:.0f}%)")
                else:
                    print("    No assignment match found")
            else:
                print(f"    Error: {result.error}")

    except Exception as e:
        print(f"Error: {e}")
        logger.exception("Email processing failed")
        sys.exit(1)


def get_student(session, student_arg: str = None) -> Student:
    """Get student from database by name or ID."""
    if student_arg:
        # Try by ID first
        if student_arg.isdigit():
            student = session.query(Student).filter_by(id=int(student_arg)).first()
            if student:
                return student

        # Try by name
        student = session.query(Student).filter(
            Student.name.ilike(f"%{student_arg}%")
        ).first()
        if student:
            return student

    # Return first student if none specified
    return session.query(Student).first()


def list_students(args):
    """List students in database."""
    session = get_session()
    students = session.query(Student).all()

    print("Students in database:")
    print("=" * 40)

    if not students:
        print("  No students found.")
        print("  Run 'python -m cli.sync' to sync from Canvas.")
        return

    for student in students:
        print(f"  ID: {student.id}, Name: {student.name}")


def main():
    parser = argparse.ArgumentParser(
        description="Process scanned homework images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # File processing
    file_parser = subparsers.add_parser("file", help="Process a single file")
    file_parser.add_argument("file", help="Path to image or PDF file")
    file_parser.add_argument("-v", "--verbose", action="store_true", help="Show raw OCR text")
    file_parser.add_argument("-o", "--output", help="Save output to file")
    file_parser.add_argument("-m", "--match", action="store_true", help="Match to Canvas assignment")
    file_parser.add_argument("-s", "--student", help="Student name or ID for matching")
    file_parser.set_defaults(func=process_file)

    # Email processing
    email_parser = subparsers.add_parser("email", help="Process emails with attachments")
    email_parser.add_argument("-s", "--student", help="Student name or ID")
    email_parser.add_argument("-q", "--query", help="Gmail search query")
    email_parser.add_argument("-m", "--max", type=int, default=10, help="Max emails to process")
    email_parser.add_argument("-o", "--output", help="Save files to directory")
    email_parser.add_argument("-l", "--list-only", action="store_true", help="List emails without processing")
    email_parser.add_argument("--no-mark", action="store_true", help="Don't mark emails as processed")
    email_parser.set_defaults(func=process_email)

    # List students
    students_parser = subparsers.add_parser("students", help="List students in database")
    students_parser.set_defaults(func=list_students)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
