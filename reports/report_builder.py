#!/usr/bin/env python3
"""
Report Builder - Build HTML reports from Canvas data.

Combines data collection, templating, and visualization.
"""

import os
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List

from jinja2 import Environment, FileSystemLoader, select_autoescape

from reports.data_collector import DataCollector
from reports.visualizations import create_grades_chart


class ReportBuilder:
    """
    Builds HTML reports for email delivery.

    Combines data from Canvas with Jinja2 templates and
    embedded visualizations.
    """

    def __init__(self, template_dir: Optional[str] = None):
        """
        Initialize report builder.

        Args:
            template_dir: Directory containing Jinja2 templates
                (uses default templates directory if not provided)
        """
        if template_dir is None:
            # Default to templates directory relative to this file
            template_dir = Path(__file__).parent.parent / "templates"

        self.template_dir = Path(template_dir)
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        self._chart_files: List[str] = []

    def build_daily_report(
        self,
        student_id: int,
        student_name: str,
        include_chart: bool = True,
        grade_alert_threshold: int = 80,
    ) -> Dict[str, Any]:
        """
        Build a complete daily report.

        Args:
            student_id: Canvas user ID
            student_name: Student's display name
            include_chart: Whether to generate grades chart
            grade_alert_threshold: Threshold for grade alerts

        Returns:
            Dict with 'html', 'subject', and 'images' keys
        """
        # Collect data
        collector = DataCollector(student_id, student_name)
        data = collector.get_report_data(grade_alert_threshold)

        # Generate chart if requested
        images = {}
        if include_chart and data["courses"]:
            chart_path = create_grades_chart(data["courses"])
            self._chart_files.append(chart_path)
            images["grades_chart"] = chart_path
            data["grades_chart"] = True

        # Render template
        template = self.env.get_template("email_daily.html")
        html = template.render(**data)

        # Build subject line
        avg = data.get("average_grade")
        missing = data.get("missing_count", 0)

        if missing > 0:
            subject = f"[Action Needed] {student_name} - {missing} Missing Assignment(s)"
        elif avg and avg >= 90:
            subject = f"Great News! {student_name} - Average: {avg}%"
        else:
            subject = f"Daily Report: {student_name}"

        return {
            "html": html,
            "subject": subject,
            "images": images,
            "data": data,
        }

    def build_weekly_report(
        self,
        student_id: int,
        student_name: str,
        include_chart: bool = True,
        grade_alert_threshold: int = 80,
    ) -> Dict[str, Any]:
        """
        Build a weekly summary report.

        For now, this is the same as daily but could be extended
        with week-over-week comparisons.

        Args:
            student_id: Canvas user ID
            student_name: Student's display name
            include_chart: Whether to generate grades chart
            grade_alert_threshold: Threshold for grade alerts

        Returns:
            Dict with 'html', 'subject', and 'images' keys
        """
        # For now, use daily report format
        # Future: Add weekly-specific template with trends
        result = self.build_daily_report(
            student_id,
            student_name,
            include_chart,
            grade_alert_threshold,
        )

        # Update subject for weekly
        result["subject"] = result["subject"].replace("Daily Report", "Weekly Report")

        return result

    def build_multi_student_report(
        self,
        students: List[Dict],
        include_charts: bool = True,
        grade_alert_threshold: int = 80,
    ) -> List[Dict[str, Any]]:
        """
        Build reports for multiple students.

        Args:
            students: List of student dicts with 'id' and 'name' keys
            include_charts: Whether to generate grades charts
            grade_alert_threshold: Threshold for grade alerts

        Returns:
            List of report dicts (one per student)
        """
        reports = []

        for student in students:
            report = self.build_daily_report(
                student["id"],
                student.get("name", "Unknown"),
                include_charts,
                grade_alert_threshold,
            )
            reports.append(report)

        return reports

    def cleanup_temp_files(self):
        """Remove temporary chart files."""
        for path in self._chart_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        self._chart_files = []


def build_and_preview_report(student_id: int, student_name: str) -> str:
    """
    Build a report and save as HTML file for preview.

    Args:
        student_id: Canvas user ID
        student_name: Student's display name

    Returns:
        Path to the saved HTML file
    """
    builder = ReportBuilder()
    result = builder.build_daily_report(student_id, student_name)

    # Save to temp file
    output_path = tempfile.mktemp(suffix=".html")
    with open(output_path, "w") as f:
        f.write(result["html"])

    return output_path


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    import webbrowser
    import canvas_api

    print("Report Builder Test")
    print("=" * 50)

    if not canvas_api.is_api_configured():
        print("Error: Canvas API not configured")
        exit(1)

    students = canvas_api.get_students()
    if not students:
        print("No students found")
        exit(1)

    # Build report for first student
    student = students[0]
    print(f"Building report for: {student.get('name')}")

    builder = ReportBuilder()
    result = builder.build_daily_report(student["id"], student.get("name", "Unknown"))

    print(f"\nSubject: {result['subject']}")
    print(f"Images: {list(result['images'].keys())}")

    # Save and open preview
    preview_path = "/tmp/canvas_report_preview.html"
    with open(preview_path, "w") as f:
        f.write(result["html"])

    print(f"\nReport saved to: {preview_path}")

    response = input("Open in browser? (y/N): ").strip().lower()
    if response == "y":
        webbrowser.open(f"file://{preview_path}")

    builder.cleanup_temp_files()
