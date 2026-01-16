#!/usr/bin/env python3
"""
Daily Debrief CLI - Show what happened today and what's coming tomorrow.

Usage:
    python -m cli.daily_debrief                    # Combined family report (default)
    python -m cli.daily_debrief --student "JJ"     # Specific student only
    python -m cli.daily_debrief --email            # Send email instead of terminal
    python -m cli.daily_debrief --preview          # Preview HTML in browser
    python -m cli.daily_debrief --date 2026-01-15  # For a specific date

Options:
    --student NAME    Show debrief for specific student only
    --email           Send email report instead of terminal output
    --preview         Preview HTML in browser (no email)
    --to EMAIL        Override recipient email address
    --date DATE       Generate debrief for specific date (YYYY-MM-DD)
"""

import argparse
import os
import sys
import webbrowser
from datetime import date, datetime
from typing import List, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import canvas_api
from config import get_config
from reports.debrief_collector import DebriefCollector, DebriefData


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Daily debrief - what happened today, what's coming tomorrow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--student",
        type=str,
        help="Show debrief for specific student (by name)",
    )
    parser.add_argument(
        "--email",
        action="store_true",
        help="Send email report instead of terminal output",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview HTML in browser instead of terminal",
    )
    parser.add_argument(
        "--to",
        type=str,
        help="Override recipient email address",
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Date for debrief (YYYY-MM-DD format, default: today)",
    )

    return parser.parse_args()


def print_header(text: str, char: str = "=", width: int = 60):
    """Print a formatted header."""
    print(char * width)
    print(f"  {text}")
    print(char * width)


def print_section(title: str, char: str = "-", width: int = 60):
    """Print a section header."""
    print(f"\n{title}")
    print(char * width)


def print_terminal_debrief(debrief: DebriefData):
    """Display debrief data in terminal format."""
    print()
    print_header(
        f"DAILY DEBRIEF: {debrief.student_name} - {debrief.day_of_week}, "
        f"{debrief.report_date.strftime('%B %d, %Y')}"
    )

    # TODAY SECTION
    print_section("WHAT HAPPENED TODAY")

    # Today's agenda content
    if debrief.today_agendas:
        for course_name, agenda in debrief.today_agendas.items():
            # Skip courses with only template content
            if _is_template_content(agenda.in_class):
                continue

            print(f"\n  {course_name}")
            if agenda.learning_objectives:
                objectives = ", ".join(agenda.learning_objectives[:3])
                print(f"    Topics: {objectives[:80]}")
            if agenda.in_class:
                for item in agenda.in_class[:3]:
                    print(f"    - {item[:70]}")
            if agenda.at_home:
                print(f"    Homework:")
                for item in agenda.at_home[:2]:
                    print(f"      - {item[:65]}")
    else:
        print("\n  No agenda content found for today.")

    # Grades posted today
    if debrief.grades_posted_today:
        print_section("GRADES POSTED TODAY")
        for grade in debrief.grades_posted_today:
            pct = grade.get("percentage", 0)
            emoji = "✓" if pct >= 70 else "⚠"
            print(
                f"  {emoji} {grade['name'][:35]}: "
                f"{grade['score']}/{grade['points_possible']} ({pct}%) - {grade['course_name']}"
            )
    else:
        print_section("GRADES POSTED TODAY")
        print("  No new grades today.")

    # Assignments due today
    if debrief.assignments_due_today:
        print_section("DUE TODAY")
        for item in debrief.assignments_due_today:
            print(
                f"  - {item['name'][:40]} - {item['course_name']} "
                f"({item['points_possible']} pts)"
            )

    # Announcements
    if debrief.announcements_today:
        print_section("ANNOUNCEMENTS")
        for ann in debrief.announcements_today:
            print(f"  - {ann['title']} ({ann['course_name']})")

    # TOMORROW SECTION
    print()
    print_header(f"TOMORROW ({debrief.tomorrow_day})", char="=")

    # Tomorrow's agenda
    if debrief.tomorrow_agendas:
        print_section("WHAT'S PLANNED")
        for course_name, agenda in debrief.tomorrow_agendas.items():
            # Skip template content
            if _is_template_content(agenda.in_class):
                continue

            print(f"\n  {course_name}")
            if agenda.learning_objectives:
                objectives = ", ".join(agenda.learning_objectives[:2])
                print(f"    Topics: {objectives[:70]}")
            if agenda.in_class:
                for item in agenda.in_class[:2]:
                    print(f"    - {item[:70]}")
    else:
        print_section("WHAT'S PLANNED")
        print("  No agenda content found for tomorrow.")

    # Due tomorrow
    if debrief.assignments_due_tomorrow:
        print_section("DUE TOMORROW")
        for item in debrief.assignments_due_tomorrow:
            print(
                f"  - {item['name'][:40]} - {item['course_name']} "
                f"({item['points_possible']} pts)"
            )

    # Missing assignments alert
    if debrief.missing_assignments:
        print_section(f"MISSING ASSIGNMENTS: {len(debrief.missing_assignments)}")
        for item in debrief.missing_assignments[:5]:
            print(
                f"  ! {item['name'][:35]} - {item['course_name']} "
                f"(Due: {item['due_date']})"
            )
        if len(debrief.missing_assignments) > 5:
            print(f"  ... and {len(debrief.missing_assignments) - 5} more")

    print(f"\n{'=' * 60}")
    print(f"  Generated: {debrief.generated_at}")
    print()


def _is_template_content(items: List[str]) -> bool:
    """Check if content appears to be template placeholder text."""
    if not items:
        return False
    template_phrases = [
        "opening activity",
        "bellringer",
        "lesson #",
        "topic / / unit",
        "links and page numbers",
        "can be deleted",
    ]
    first_item = items[0].lower() if items else ""
    return any(phrase in first_item for phrase in template_phrases)


def _is_school_wide_course(course_name: str) -> bool:
    """Check if this is a school-wide or redundant course to filter out."""
    skip_patterns = [
        "thales academy",
        "school-wide",
        "all students",
        "k-8",
        "k–8",
        "specials",  # Specials schedule is shown in Homeroom
    ]
    name_lower = course_name.lower()
    return any(pattern in name_lower for pattern in skip_patterns)


def _get_special_name(agenda) -> Optional[str]:
    """Extract the name of today's special from agenda content."""
    if agenda is None:
        return None

    # Check learning objectives first (often has "Specials: Spanish" etc)
    for item in (agenda.learning_objectives or []):
        if "specials:" in item.lower():
            # Extract what comes after "Specials:"
            parts = item.split(":", 1)
            if len(parts) > 1:
                return parts[1].strip()[:20]
        # Direct match for special names
        specials = ["spanish", "pe", "art", "music", "technology", "library"]
        item_lower = item.lower()
        for special in specials:
            if special in item_lower:
                return special.capitalize()

    # Check in_class items
    for item in (agenda.in_class or []):
        if "specials:" in item.lower():
            parts = item.split(":", 1)
            if len(parts) > 1:
                return parts[1].strip()[:20]

    return None


def generate_html_debrief(debrief: DebriefData) -> str:
    """Generate HTML version of debrief."""
    # Inline template for now - can be moved to templates/ later
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Daily Debrief - {debrief.student_name}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
            padding: 10px 0;
            border-bottom: 1px solid #eee;
        }}
        h3 {{
            color: #2980b9;
            margin: 15px 0 10px 0;
        }}
        .section {{
            margin: 20px 0;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
        }}
        .section.tomorrow {{
            background: #e8f4f8;
        }}
        .section.alert {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
        }}
        .course-block {{
            margin: 15px 0;
            padding: 10px 15px;
            background: white;
            border-radius: 6px;
            border-left: 3px solid #3498db;
        }}
        ul {{
            margin: 5px 0;
            padding-left: 20px;
        }}
        li {{
            margin: 5px 0;
            color: #555;
        }}
        .grade-item {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
        }}
        .grade-score {{
            font-weight: bold;
        }}
        .grade-good {{ color: #27ae60; }}
        .grade-warn {{ color: #e74c3c; }}
        .empty-message {{
            color: #7f8c8d;
            font-style: italic;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 15px;
            border-top: 1px solid #eee;
            color: #95a5a6;
            font-size: 12px;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Daily Debrief: {debrief.student_name}</h1>
        <p style="color: #7f8c8d;">{debrief.day_of_week}, {debrief.report_date.strftime('%B %d, %Y')}</p>

        <h2>What Happened Today</h2>
        <div class="section">
"""

    # Today's agendas
    agenda_count = 0
    for course_name, agenda in debrief.today_agendas.items():
        if _is_template_content(agenda.in_class):
            continue
        agenda_count += 1
        html += f'<div class="course-block"><h3>{course_name}</h3>'
        if agenda.in_class:
            html += "<strong>In Class:</strong><ul>"
            for item in agenda.in_class[:3]:
                html += f"<li>{item}</li>"
            html += "</ul>"
        if agenda.at_home:
            html += "<strong>Homework:</strong><ul>"
            for item in agenda.at_home[:2]:
                html += f"<li>{item}</li>"
            html += "</ul>"
        html += "</div>"

    if agenda_count == 0:
        html += '<p class="empty-message">No agenda content found for today.</p>'

    html += "</div>"

    # Grades posted today
    html += "<h2>Grades Posted Today</h2><div class=\"section\">"
    if debrief.grades_posted_today:
        for grade in debrief.grades_posted_today:
            pct = grade.get("percentage", 0)
            cls = "grade-good" if pct >= 70 else "grade-warn"
            html += f"""
            <div class="grade-item">
                <span>{grade['name']} - {grade['course_name']}</span>
                <span class="grade-score {cls}">{grade['score']}/{grade['points_possible']} ({pct}%)</span>
            </div>"""
    else:
        html += '<p class="empty-message">No new grades today.</p>'
    html += "</div>"

    # Due today
    if debrief.assignments_due_today:
        html += "<h2>Due Today</h2><div class=\"section\"><ul>"
        for item in debrief.assignments_due_today:
            html += f"<li>{item['name']} - {item['course_name']} ({item['points_possible']} pts)</li>"
        html += "</ul></div>"

    # Tomorrow section
    html += f"""
        <h2>Tomorrow ({debrief.tomorrow_day})</h2>
        <div class="section tomorrow">
    """

    agenda_count = 0
    for course_name, agenda in debrief.tomorrow_agendas.items():
        if _is_template_content(agenda.in_class):
            continue
        agenda_count += 1
        html += f'<div class="course-block"><h3>{course_name}</h3>'
        if agenda.in_class:
            html += "<ul>"
            for item in agenda.in_class[:2]:
                html += f"<li>{item}</li>"
            html += "</ul>"
        html += "</div>"

    if agenda_count == 0:
        html += '<p class="empty-message">No agenda content found for tomorrow.</p>'

    html += "</div>"

    # Due tomorrow
    if debrief.assignments_due_tomorrow:
        html += "<h2>Due Tomorrow</h2><div class=\"section\"><ul>"
        for item in debrief.assignments_due_tomorrow:
            html += f"<li>{item['name']} - {item['course_name']} ({item['points_possible']} pts)</li>"
        html += "</ul></div>"

    # Missing assignments
    if debrief.missing_assignments:
        html += f"""
        <h2>Missing Assignments ({len(debrief.missing_assignments)})</h2>
        <div class="section alert"><ul>
        """
        for item in debrief.missing_assignments[:5]:
            html += f"<li>{item['name']} - {item['course_name']} (Due: {item['due_date']})</li>"
        if len(debrief.missing_assignments) > 5:
            html += f"<li>...and {len(debrief.missing_assignments) - 5} more</li>"
        html += "</ul></div>"

    html += f"""
        <div class="footer">
            Generated by Canvas Parent CLI at {debrief.generated_at}
        </div>
    </div>
</body>
</html>
"""
    return html


def preview_debrief(debrief: DebriefData) -> bool:
    """Generate and preview debrief in browser."""
    try:
        html = generate_html_debrief(debrief)
        preview_path = f"/tmp/canvas_debrief_{debrief.student_name.replace(' ', '_')}.html"

        with open(preview_path, "w") as f:
            f.write(html)

        print(f"Preview saved to: {preview_path}")
        webbrowser.open(f"file://{preview_path}")
        return True

    except Exception as e:
        print(f"Error generating preview: {e}")
        return False


def send_debrief_email(
    debrief: DebriefData, recipients: List[str]
) -> bool:
    """Generate and send debrief email."""
    try:
        from google_services.gmail_service import GmailService

        html = generate_html_debrief(debrief)

        # Build subject line
        subject = f"Daily Debrief: {debrief.student_name} - {debrief.day_of_week}"
        if debrief.missing_assignments:
            subject = f"[Action Needed] {subject}"

        print(f"Subject: {subject}")
        print(f"Sending to: {', '.join(recipients)}")

        gmail = GmailService()
        result = gmail.send_html_email(
            to=recipients,
            subject=subject,
            html_body=html,
        )

        print(f"Email sent! Message ID: {result.get('id')}")
        return True

    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def print_combined_debrief(debriefs: List[DebriefData]):
    """Display combined family debrief in terminal format."""
    if not debriefs:
        return

    report_date = debriefs[0].report_date
    day_of_week = debriefs[0].day_of_week
    tomorrow_day = debriefs[0].tomorrow_day

    print()
    print_header(f"FAMILY DEBRIEF - {day_of_week}, {report_date.strftime('%B %d, %Y')}")

    # WHAT THEY DID TODAY - class by class per student
    for debrief in debriefs:
        first_name = debrief.student_name.split()[0]
        print_section(f"{first_name.upper()}'S DAY")

        # Show ALL courses
        for course_name, agenda in debrief.all_courses_today.items():
            # Skip school-wide info courses
            if _is_school_wide_course(course_name):
                continue

            # Shorten course name
            short_course = course_name.split(" - ")[0] if " - " in course_name else course_name
            short_course = short_course.replace("3rd Grade", "").strip()

            print(f"\n  {short_course}")

            if agenda is None:
                # No agenda page found for this course
                print("    (No agenda page)")
            elif _is_template_content(agenda.in_class):
                # Has agenda page but template content
                print("    (No detailed agenda posted)")
            else:
                # Show topics, but clean up "Specials:" prefix for Homeroom
                if agenda.learning_objectives:
                    topics = []
                    for obj in agenda.learning_objectives[:3]:
                        # Clean up "Specials: Spanish" -> "Spanish" for Homeroom
                        if obj.lower().startswith("specials:"):
                            clean = obj.split(":", 1)[1].strip()
                            topics.append(f"Specials: {clean}")
                        else:
                            topics.append(obj)
                    print(f"    Topics: {', '.join(topics)[:65]}")
                if agenda.in_class:
                    for item in agenda.in_class[:3]:
                        # Clean up "Specials: PE" items
                        if item.lower().startswith("specials:"):
                            clean = item.split(":", 1)[1].strip()
                            print(f"    - Specials: {clean[:60]}")
                        else:
                            print(f"    - {item[:65]}")
                if agenda.at_home:
                    print(f"    Homework:")
                    for item in agenda.at_home[:2]:
                        print(f"      * {item[:60]}")

    # GRADES POSTED TODAY
    all_grades = []
    for debrief in debriefs:
        first_name = debrief.student_name.split()[0]
        for grade in debrief.grades_posted_today:
            grade["student"] = first_name
            all_grades.append(grade)

    print_section("GRADES POSTED TODAY")
    if all_grades:
        for grade in all_grades:
            pct = grade.get("percentage", 0)
            emoji = "A" if pct >= 90 else "B" if pct >= 80 else "C" if pct >= 70 else "!"
            short_course = grade['course_name'].split(" - ")[0]
            print(
                f"  [{emoji}] {grade['student']}: {grade['name'][:30]} - "
                f"{grade['score']:.0f}/{grade['points_possible']:.0f} ({pct:.0f}%)"
            )
    else:
        print("  No new grades today.")

    # HOMEWORK DUE TODAY
    all_due_today = []
    for debrief in debriefs:
        first_name = debrief.student_name.split()[0]
        for item in debrief.assignments_due_today:
            item["student"] = first_name
            all_due_today.append(item)

    if all_due_today:
        print_section("DUE TODAY")
        for item in all_due_today:
            print(f"  - {item['student']}: {item['name'][:40]} ({item['course_name'].split(' - ')[0]})")

    # REST OF WEEK OUTLOOK
    print()
    print_header(f"REST OF WEEK", char="=")

    # Get upcoming assignments for rest of week
    print_section(f"TOMORROW ({tomorrow_day})")
    for debrief in debriefs:
        first_name = debrief.student_name.split()[0]
        has_content = False

        for course_name, agenda in debrief.tomorrow_agendas.items():
            if _is_template_content(agenda.in_class):
                continue
            if agenda.learning_objectives or agenda.in_class:
                has_content = True
                short_course = course_name.split(" - ")[0].replace("3rd Grade", "").strip()
                if agenda.learning_objectives:
                    topics = ", ".join(agenda.learning_objectives[:2])
                    print(f"  {first_name} - {short_course}: {topics[:45]}")
                elif agenda.in_class:
                    print(f"  {first_name} - {short_course}: {agenda.in_class[0][:45]}")

    # Upcoming assignments this week
    all_upcoming = []
    for debrief in debriefs:
        first_name = debrief.student_name.split()[0]
        for item in debrief.assignments_due_tomorrow:
            item["student"] = first_name
            all_upcoming.append(item)

    if all_upcoming:
        print_section("DUE TOMORROW")
        for item in all_upcoming:
            print(f"  - {item['student']}: {item['name'][:35]} ({item['course_name'].split(' - ')[0]})")

    # MISSING ASSIGNMENTS
    all_missing = []
    for debrief in debriefs:
        first_name = debrief.student_name.split()[0]
        for item in debrief.missing_assignments:
            item["student"] = first_name
            all_missing.append(item)

    if all_missing:
        print_section(f"MISSING ASSIGNMENTS ({len(all_missing)} total)")
        for item in all_missing[:6]:
            print(f"  ! {item['student']}: {item['name'][:30]} - Due: {item['due_date']}")
        if len(all_missing) > 6:
            print(f"  ... and {len(all_missing) - 6} more")

    print(f"\n{'=' * 60}")
    print(f"  Generated: {debriefs[0].generated_at}")
    print()


def _get_logo_base64() -> str:
    """Get base64 encoded logo image."""
    import base64
    logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "images", "WDYTYGS.png")
    try:
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except:
        return ""


def generate_combined_html(debriefs: List[DebriefData]) -> str:
    """Generate table-based HTML family debrief - aligned rows with shared headers."""
    if not debriefs:
        return ""

    report_date = debriefs[0].report_date
    day_of_week = debriefs[0].day_of_week
    logo_b64 = _get_logo_base64()

    # Prepare student data
    students = []
    for debrief in debriefs:
        first_name = debrief.student_name.split()[0]
        students.append({
            "name": first_name,
            "debrief": debrief,
            "grades": debrief.grades_posted_today,
            "missing": debrief.missing_assignments,
        })

    colors = {"jj": "#9b59b6", "william": "#27ae60"}
    num_students = len(students)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Family Debrief - {report_date.strftime('%b %d')}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; line-height: 1.4; color: #333; background: #f4f4f4; margin: 0; padding: 12px; }}
.container {{ background: #fff; border-radius: 8px; max-width: 680px; margin: 0 auto; overflow: hidden; }}
.header {{ background: linear-gradient(135deg, #3498db, #2980b9); color: white; padding: 14px 20px; }}
.header h1 {{ margin: 0; font-size: 18px; font-weight: 600; }}
.header .date {{ opacity: 0.9; font-size: 12px; }}
table {{ width: 100%; border-collapse: collapse; }}
.name-row td {{ padding: 12px 14px 8px; font-size: 16px; font-weight: 600; border-bottom: 3px solid #3498db; }}
.section-row td {{ padding: 10px 14px 4px; font-size: 11px; font-weight: 600; color: #888; text-transform: uppercase; letter-spacing: 0.5px; background: #fafafa; }}
.content-row td {{ padding: 0 14px; vertical-align: top; }}
.content-row td:first-child {{ border-right: 2px solid #ccc; }}
.item {{ font-size: 13px; padding: 6px 0; border-bottom: 1px solid #ddd; }}
.item:last-child {{ border-bottom: none; }}
.item-title {{ font-weight: 500; color: #333; }}
.item-sub {{ color: #666; font-size: 12px; }}
.grade {{ display: flex; justify-content: space-between; }}
.score {{ font-weight: 600; }}
.g-a {{ color: #27ae60; }} .g-b {{ color: #3498db; }} .g-c {{ color: #f39c12; }} .g-d {{ color: #e74c3c; }}
.missing {{ background: #fef3cd; border-radius: 4px; padding: 5px 8px; margin: 3px 0; font-size: 12px; color: #856404; }}
.homework {{ background: #e8f4fd; border-left: 3px solid #3498db; padding-left: 8px; margin: 4px 0; }}
.test-alert {{ background: #f8d7da; border-left: 3px solid #dc3545; padding: 6px 8px; margin: 4px 0; color: #721c24; }}
.hw-due {{ background: #fff3cd; border-left: 3px solid #ffc107; padding-left: 8px; margin: 4px 0; }}
.upcoming-test {{ background: #e2e3e5; border-radius: 4px; padding: 5px 8px; margin: 3px 0; font-size: 12px; }}
.empty {{ color: #aaa; font-style: italic; font-size: 12px; padding: 6px 0; }}
.footer {{ text-align: center; padding: 10px; color: #aaa; font-size: 10px; border-top: 1px solid #eee; }}
.spacer td {{ height: 8px; }}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>Family Debrief</h1>
<div class="date">{day_of_week}, {report_date.strftime('%B %d, %Y')}</div>
</div>
<table>
<tr class="name-row">
"""

    # Student name headers
    for s in students:
        color = colors.get(s["name"].lower(), "#3498db")
        html += f'<td style="border-bottom-color: {color};">{s["name"]}</td>'
    html += '</tr>'

    # Check if any student has missing assignments
    any_missing = any(s["missing"] for s in students)
    if any_missing:
        html += '<tr class="section-row"><td colspan="' + str(num_students) + '">⚠ Missing</td></tr>'
        html += '<tr class="content-row">'
        for s in students:
            html += '<td>'
            if s["missing"]:
                for m in s["missing"][:3]:
                    html += f'<div class="missing">{m["name"]}</div>'
            else:
                html += '<div class="empty">None</div>'
            html += '</td>'
        html += '</tr><tr class="spacer"><td></td></tr>'

    # Tests Today section (prominent alert)
    any_tests_today = any(s["debrief"].tests_today for s in students)
    if any_tests_today:
        html += f'<tr class="section-row" style="background:#f8d7da;"><td colspan="{num_students}">🚨 TESTS TODAY</td></tr>'
        html += '<tr class="content-row">'
        for s in students:
            html += '<td>'
            if s["debrief"].tests_today:
                for test in s["debrief"].tests_today:
                    html += f'<div class="test-alert"><strong>{test["course"]}</strong>: {test["description"][:50]}</div>'
            else:
                html += '<div class="empty">No tests</div>'
            html += '</td>'
        html += '</tr><tr class="spacer"><td></td></tr>'

    # Homework Due Today section (yesterday's homework)
    any_hw_due = any(s["debrief"].homework_due_today for s in students)
    if any_hw_due:
        html += f'<tr class="section-row"><td colspan="{num_students}">✅ Homework Due Today</td></tr>'
        html += '<tr class="content-row">'
        for s in students:
            html += '<td>'
            hw_due = s["debrief"].homework_due_today
            if hw_due:
                for course, items in hw_due.items():
                    for item in items[:2]:
                        html += f'<div class="item hw-due"><div class="item-title">{course}</div><div class="item-sub">{item[:60]}</div></div>'
            else:
                html += '<div class="empty">None due</div>'
            html += '</td>'
        html += '</tr><tr class="spacer"><td></td></tr>'

    # Today section
    html += f'<tr class="section-row"><td colspan="{num_students}">Today\'s Classes</td></tr>'
    html += '<tr class="content-row">'
    for s in students:
        html += '<td>'
        has_content = False
        for course_name, agenda in s["debrief"].today_agendas.items():
            if _is_template_content(agenda.in_class):
                continue
            has_content = True
            short_course = course_name.split(" - ")[0].replace("3rd Grade", "").strip()
            detail = ""
            if agenda.in_class:
                detail = agenda.in_class[0][:60]
            elif agenda.learning_objectives:
                detail = agenda.learning_objectives[0][:60]
            html += f'<div class="item"><div class="item-title">{short_course}</div>'
            if detail:
                html += f'<div class="item-sub">{detail}</div>'
            html += '</div>'
        if not has_content:
            html += '<div class="empty">No agenda</div>'
        html += '</td>'
    html += '</tr><tr class="spacer"><td></td></tr>'

    # Tonight's Homework section (assigned today, do tonight, due tomorrow)
    html += f'<tr class="section-row"><td colspan="{num_students}">📚 Do Tonight (Due Tomorrow)</td></tr>'
    html += '<tr class="content-row">'
    for s in students:
        html += '<td>'
        homework_items = []
        for course_name, agenda in s["debrief"].today_agendas.items():
            if agenda.at_home:
                short_course = course_name.split(" - ")[0].replace("3rd Grade", "").strip()
                for hw in agenda.at_home[:2]:
                    homework_items.append((short_course, hw))
        if homework_items:
            for course, hw in homework_items[:5]:
                html += f'<div class="item homework"><div class="item-title">{course}</div><div class="item-sub">{hw[:70]}</div></div>'
        else:
            html += '<div class="empty">No homework</div>'
        html += '</td>'
    html += '</tr><tr class="spacer"><td></td></tr>'

    # Grades section
    html += f'<tr class="section-row"><td colspan="{num_students}">Grades Posted Today</td></tr>'
    html += '<tr class="content-row">'
    for s in students:
        html += '<td>'
        if s["grades"]:
            for g in s["grades"][:4]:
                pct = g.get("percentage", 0)
                cls = "g-a" if pct >= 90 else "g-b" if pct >= 80 else "g-c" if pct >= 70 else "g-d"
                html += f'<div class="item grade"><span class="item-title">{g["name"]}</span><span class="score {cls}">{pct:.0f}%</span></div>'
        else:
            html += '<div class="empty">None today</div>'
        html += '</td>'
    html += '</tr><tr class="spacer"><td></td></tr>'

    # Test Tomorrow section (study tonight!)
    any_tests_tomorrow = any(s["debrief"].tests_tomorrow for s in students)
    if any_tests_tomorrow:
        html += f'<tr class="section-row" style="background:#fff3cd;"><td colspan="{num_students}">📖 TEST TOMORROW - Study Tonight!</td></tr>'
        html += '<tr class="content-row">'
        for s in students:
            html += '<td>'
            if s["debrief"].tests_tomorrow:
                for test in s["debrief"].tests_tomorrow:
                    html += f'<div class="test-alert" style="background:#fff3cd;border-color:#ffc107;color:#856404;"><strong>{test["course"]}</strong>: {test["description"][:50]}</div>'
            else:
                html += '<div class="empty">No tests</div>'
            html += '</td>'
        html += '</tr><tr class="spacer"><td></td></tr>'

    # Next Test section (upcoming)
    any_next_test = any(s["debrief"].next_test for s in students)
    if any_next_test:
        html += f'<tr class="section-row"><td colspan="{num_students}">📅 Next Test</td></tr>'
        html += '<tr class="content-row">'
        for s in students:
            html += '<td>'
            test = s["debrief"].next_test
            if test:
                html += f'<div class="upcoming-test"><strong>{test["day"]}</strong> - {test["course"]}: {test["description"][:40]}</div>'
            else:
                html += '<div class="empty">None scheduled</div>'
            html += '</td>'
        html += '</tr><tr class="spacer"><td></td></tr>'

    # Tomorrow's Preview section
    html += f'<tr class="section-row"><td colspan="{num_students}">Tomorrow\'s Preview</td></tr>'
    html += '<tr class="content-row">'
    for s in students:
        html += '<td>'
        has_content = False
        for course_name, agenda in s["debrief"].tomorrow_agendas.items():
            if _is_template_content(agenda.in_class):
                continue
            has_content = True
            short_course = course_name.split(" - ")[0].replace("3rd Grade", "").strip()
            detail = ""
            if agenda.in_class:
                detail = agenda.in_class[0][:60]
            elif agenda.learning_objectives:
                detail = agenda.learning_objectives[0][:60]
            html += f'<div class="item"><div class="item-title">{short_course}</div>'
            if detail:
                html += f'<div class="item-sub">{detail}</div>'
            html += '</div>'
        if not has_content:
            html += '<div class="empty">No preview</div>'
        html += '</td>'
    html += '</tr>'

    # Logo at bottom
    logo_html = ""
    if logo_b64:
        logo_html = f'''
<div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #1a1a2e, #16213e);">
<img src="data:image/png;base64,{logo_b64}" alt="WDYTYGS" style="width: 200px; height: 200px; border-radius: 12px;">
</div>'''

    html += f'</table>{logo_html}<div class="footer">Canvas Parent CLI • {debriefs[0].generated_at}</div></div></body></html>'
    return html


def preview_combined_debrief(debriefs: List[DebriefData]) -> bool:
    """Generate and preview combined debrief in browser."""
    try:
        html = generate_combined_html(debriefs)
        preview_path = "/tmp/canvas_family_debrief.html"

        with open(preview_path, "w") as f:
            f.write(html)

        print(f"Preview saved to: {preview_path}")
        webbrowser.open(f"file://{preview_path}")
        return True

    except Exception as e:
        print(f"Error generating preview: {e}")
        return False


def send_combined_email(debriefs: List[DebriefData], recipients: List[str]) -> bool:
    """Generate and send combined family debrief email."""
    try:
        from google_services.gmail_service import GmailService

        html = generate_combined_html(debriefs)
        report_date = debriefs[0].report_date
        day_of_week = debriefs[0].day_of_week

        # Check for missing assignments
        total_missing = sum(len(d.missing_assignments) for d in debriefs)

        subject = f"Family Debrief - {day_of_week}, {report_date.strftime('%b %d')}"
        if total_missing:
            subject = f"[{total_missing} Missing] {subject}"

        print(f"Subject: {subject}")
        print(f"Sending to: {', '.join(recipients)}")

        gmail = GmailService()
        result = gmail.send_html_email(
            to=recipients,
            subject=subject,
            html_body=html,
        )

        print(f"Email sent! Message ID: {result.get('id')}")
        return True

    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def main():
    """Main entry point."""
    args = parse_args()

    print("Canvas Parent CLI - Daily Debrief")
    print("=" * 50)

    # Check Canvas API configuration
    if not canvas_api.is_api_configured():
        print("Error: Canvas API not configured")
        print("Set CANVAS_API_URL and CANVAS_API_KEY in .env file")
        sys.exit(1)

    # Parse target date
    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
            print(f"Generating debrief for: {target_date}")
        except ValueError:
            print(f"Error: Invalid date format '{args.date}'. Use YYYY-MM-DD.")
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

    # Get recipients for email
    recipients = None
    if args.email:
        config = get_config()
        recipients = [args.to] if args.to else config.email.recipients
        if not recipients:
            print("Error: No email recipients configured")
            print("Set EMAIL_RECIPIENTS in .env or use --to flag")
            sys.exit(1)

    # Collect debrief data for all students
    debriefs = []
    for student in students:
        student_id = student["id"]
        student_name = student.get("name", "Unknown")

        print(f"Collecting data for: {student_name}...")

        collector = DebriefCollector(student_id, student_name)
        debrief = collector.collect(target_date)
        debriefs.append(debrief)

    # Single student mode (--student flag)
    if args.student or len(debriefs) == 1:
        debrief = debriefs[0]
        if args.preview:
            success = preview_debrief(debrief)
        elif args.email:
            success = send_debrief_email(debrief, recipients)
        else:
            print_terminal_debrief(debrief)
            success = True

        sys.exit(0 if success else 1)

    # Combined family report (default for multiple students)
    if args.preview:
        success = preview_combined_debrief(debriefs)
    elif args.email:
        success = send_combined_email(debriefs, recipients)
    else:
        print_combined_debrief(debriefs)
        success = True

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
