#!/usr/bin/env python3
"""
Assign Document CLI - Manually assign scanned documents to students.

Commands:
    python -m cli.assign_document list                    List pending documents
    python -m cli.assign_document <doc_id> --student JJ   Assign document to student
"""

import argparse
import logging
import sys

from database.connection import get_session
from database.models import Student, ScannedDocument

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_student(session, student_arg: str) -> Student:
    """Get student from database by name or ID."""
    if student_arg.isdigit():
        student = session.query(Student).filter_by(id=int(student_arg)).first()
        if student:
            return student

    # Try by name (partial match)
    student = session.query(Student).filter(
        Student.name.ilike(f"%{student_arg}%")
    ).first()
    return student


def cmd_list(args):
    """List documents pending assignment."""
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

    for doc in pending_docs:
        print(f"ID: {doc.id}")
        print(f"  File: {doc.file_name}")
        print(f"  Scanned: {doc.scan_date.strftime('%Y-%m-%d %H:%M') if doc.scan_date else 'Unknown'}")
        if doc.detected_title:
            print(f"  Title: {doc.detected_title}")
        if doc.detected_score is not None:
            score_str = f"{doc.detected_score}"
            if doc.detected_max_score:
                score_str += f"/{doc.detected_max_score}"
            print(f"  Score: {score_str}")
        if doc.ocr_text:
            preview = doc.ocr_text[:100].replace("\n", " ")
            if len(doc.ocr_text) > 100:
                preview += "..."
            print(f"  Preview: {preview}")
        print()

    print("Available students:")
    for s in students:
        print(f"  - {s.name} (ID: {s.id})")

    print("\nTo assign: python -m cli.assign_document <doc_id> --student <name>")


def cmd_assign(args):
    """Assign a document to a student."""
    session = get_session()

    # Get the document
    doc = session.query(ScannedDocument).filter_by(id=args.doc_id).first()
    if not doc:
        print(f"Error: Document {args.doc_id} not found")
        sys.exit(1)

    # Get the student
    student = get_student(session, args.student)
    if not student:
        print(f"Error: Student '{args.student}' not found")
        students = session.query(Student).all()
        print("\nAvailable students:")
        for s in students:
            print(f"  - {s.name} (ID: {s.id})")
        sys.exit(1)

    # Check if already assigned
    if doc.student_id:
        current_student = session.query(Student).filter_by(id=doc.student_id).first()
        if current_student:
            print(f"Warning: Document already assigned to {current_student.name}")
            if not args.force:
                print("Use --force to reassign")
                sys.exit(1)

    # Assign the document
    doc.student_id = student.id

    # Try to match to an assignment
    if args.match:
        from scanner.matcher import AssignmentMatcher
        from scanner.parser import GradeParser, ParsedDocument

        # Create a ParsedDocument from the stored data
        parsed = ParsedDocument(
            title=doc.detected_title,
            date=doc.detected_date,
        )
        if doc.detected_score is not None:
            from scanner.parser import ParsedScore
            parsed.score = ParsedScore(
                earned=doc.detected_score,
                possible=doc.detected_max_score or 100,
                percentage=(doc.detected_score / (doc.detected_max_score or 100)) * 100,
            )

        matcher = AssignmentMatcher(session)
        match = matcher.find_match(parsed, student.id)

        if match.assignment:
            doc.assignment_id = match.assignment.id
            doc.match_confidence = match.confidence
            doc.match_method = match.method
            print(f"Matched to assignment: {match.assignment.name} ({match.confidence:.0f}%)")

    session.commit()

    print(f"\nDocument {doc.id} assigned to {student.name}")
    print(f"  File: {doc.file_name}")
    if doc.assignment_id:
        assignment = session.query(ScannedDocument).filter_by(id=doc.assignment_id).first()
        if assignment:
            print(f"  Assignment: {assignment.name}")


def main():
    parser = argparse.ArgumentParser(
        description="Assign scanned documents to students",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  List pending documents:
    python -m cli.assign_document list

  Assign document to student:
    python -m cli.assign_document 5 --student JJ

  Assign and match to Canvas assignment:
    python -m cli.assign_document 5 --student JJ --match
"""
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List pending documents")
    list_parser.set_defaults(func=cmd_list)

    # Assign command (default when doc_id provided)
    parser.add_argument("doc_id", nargs="?", type=int, help="Document ID to assign")
    parser.add_argument("-s", "--student", help="Student name or ID")
    parser.add_argument("-m", "--match", action="store_true", help="Try to match to Canvas assignment")
    parser.add_argument("-f", "--force", action="store_true", help="Force reassignment")

    args = parser.parse_args()

    if args.command == "list":
        args.func(args)
    elif args.doc_id:
        if not args.student:
            print("Error: --student is required when assigning")
            sys.exit(1)
        cmd_assign(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
