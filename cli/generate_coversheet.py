#!/usr/bin/env python3
"""
Generate Cover Sheet CLI - Create printable cover sheets for student identification.

Each student gets a simple PDF cover sheet with their name in large text.
Place on top of homework before scanning for automatic student detection.

Commands:
    python -m cli.generate_coversheet                    Generate for all students
    python -m cli.generate_coversheet --student JJ       Generate for specific student
    python -m cli.generate_coversheet --output ~/Desktop Generate to specific folder
"""

import argparse
import logging
import sys
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

from database.connection import get_session
from database.models import Student

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def generate_coversheet(student: Student, output_dir: Path) -> Path:
    """
    Generate a cover sheet PDF for a student.

    Args:
        student: Student database record
        output_dir: Directory to save PDF

    Returns:
        Path to generated PDF
    """
    # Use first name for cleaner display
    first_name = student.name.split()[0].upper()

    # Output filename
    filename = f"coversheet_{first_name.lower()}.pdf"
    output_path = output_dir / filename

    # Create PDF
    c = canvas.Canvas(str(output_path), pagesize=letter)
    width, height = letter

    # Background - light gray header area
    c.setFillColor(HexColor("#f5f5f5"))
    c.rect(0, height - 3*inch, width, 3*inch, fill=True, stroke=False)

    # Student name - large and bold
    c.setFillColor(HexColor("#333333"))
    c.setFont("Helvetica-Bold", 120)

    # Center the name
    text_width = c.stringWidth(first_name, "Helvetica-Bold", 120)
    x = (width - text_width) / 2
    y = height - 2*inch

    c.drawString(x, y, first_name)

    # Full name smaller below
    c.setFont("Helvetica", 24)
    c.setFillColor(HexColor("#666666"))
    full_name_width = c.stringWidth(student.name, "Helvetica", 24)
    c.drawString((width - full_name_width) / 2, y - 50, student.name)

    # Instructions
    c.setFont("Helvetica", 14)
    c.setFillColor(HexColor("#999999"))
    instruction = "Place homework documents below this sheet before scanning"
    instr_width = c.stringWidth(instruction, "Helvetica", 14)
    c.drawString((width - instr_width) / 2, height - 2.8*inch, instruction)

    # Divider line
    c.setStrokeColor(HexColor("#dddddd"))
    c.setLineWidth(2)
    c.line(1*inch, height - 3*inch, width - 1*inch, height - 3*inch)

    # Footer
    c.setFont("Helvetica", 10)
    c.setFillColor(HexColor("#cccccc"))
    footer = "Canvas Parent CLI - Homework Scanner Cover Sheet"
    footer_width = c.stringWidth(footer, "Helvetica", 10)
    c.drawString((width - footer_width) / 2, 0.5*inch, footer)

    c.save()

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate cover sheets for student identification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Generate for all students:
    python -m cli.generate_coversheet

  Generate for specific student:
    python -m cli.generate_coversheet --student JJ

  Generate to specific folder:
    python -m cli.generate_coversheet --output ~/Desktop/
"""
    )

    parser.add_argument(
        "-s", "--student",
        help="Student name or ID (generates for all if not specified)"
    )
    parser.add_argument(
        "-o", "--output",
        default=".",
        help="Output directory for PDFs (default: current directory)"
    )

    args = parser.parse_args()

    # Setup output directory
    output_dir = Path(args.output).expanduser().resolve()
    if not output_dir.exists():
        output_dir.mkdir(parents=True)

    # Get students from database
    session = get_session()

    if args.student:
        # Find specific student
        if args.student.isdigit():
            student = session.query(Student).filter_by(id=int(args.student)).first()
        else:
            student = session.query(Student).filter(
                Student.name.ilike(f"%{args.student}%")
            ).first()

        if not student:
            print(f"Error: Student '{args.student}' not found")
            students = session.query(Student).all()
            print("\nAvailable students:")
            for s in students:
                print(f"  - {s.name} (ID: {s.id})")
            sys.exit(1)

        students = [student]
    else:
        students = session.query(Student).all()

    if not students:
        print("Error: No students found in database")
        sys.exit(1)

    # Generate cover sheets
    print("Generating Cover Sheets")
    print("=" * 50)

    for student in students:
        output_path = generate_coversheet(student, output_dir)
        print(f"  ✓ {student.name}: {output_path}")

    print(f"\nGenerated {len(students)} cover sheet(s) in: {output_dir}")
    print("\nUsage:")
    print("  1. Print the cover sheet(s)")
    print("  2. Place on top of homework before scanning")
    print("  3. The scanner will auto-detect the student")


if __name__ == "__main__":
    main()
