#!/usr/bin/env python3
"""
Assignment Web Endpoint - One-click document assignment from email links.

Run with: python -m web.assign
"""

import logging
from flask import Flask, request, redirect, render_template_string

from database.connection import get_session
from database.models import Student, ScannedDocument
from scanner.notifications import verify_assign_token
from config import get_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# HTML Templates
SUCCESS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Document Assigned</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: #f5f5f5;
        }
        .container {
            text-align: center;
            padding: 40px;
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            max-width: 400px;
        }
        .success {
            color: #4CAF50;
            font-size: 48px;
            margin-bottom: 20px;
        }
        h1 { color: #333; margin: 0 0 10px; }
        p { color: #666; margin: 10px 0; }
        .details {
            background: #f9f9f9;
            padding: 15px;
            border-radius: 5px;
            margin-top: 20px;
            text-align: left;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="success">✓</div>
        <h1>Document Assigned!</h1>
        <p>The homework scan has been assigned to <strong>{{ student_name }}</strong>.</p>
        <div class="details">
            <p><strong>File:</strong> {{ file_name }}</p>
            {% if title %}
            <p><strong>Title:</strong> {{ title }}</p>
            {% endif %}
        </div>
        <p style="margin-top: 20px; font-size: 14px; color: #999;">You can close this page.</p>
    </div>
</body>
</html>
"""

ERROR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Assignment Error</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: #f5f5f5;
        }
        .container {
            text-align: center;
            padding: 40px;
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            max-width: 400px;
        }
        .error {
            color: #f44336;
            font-size: 48px;
            margin-bottom: 20px;
        }
        h1 { color: #333; margin: 0 0 10px; }
        p { color: #666; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="error">✗</div>
        <h1>Assignment Failed</h1>
        <p>{{ error }}</p>
        <p style="margin-top: 20px; font-size: 14px; color: #999;">
            Please try again or assign manually using the CLI.
        </p>
    </div>
</body>
</html>
"""


@app.route("/")
def index():
    """Health check endpoint."""
    return "Canvas Parent CLI - Assignment Service"


@app.route("/assign/<token>/<int:student_id>")
def assign_document(token, student_id):
    """
    Assign a document to a student.

    Args:
        token: Signed token containing document ID
        student_id: ID of the student to assign to
    """
    # Verify token
    doc_id = verify_assign_token(token)
    if doc_id is None:
        return render_template_string(ERROR_TEMPLATE, error="Invalid or expired link. Please request a new assignment email.")

    session = get_session()

    # Get document
    doc = session.query(ScannedDocument).filter_by(id=doc_id).first()
    if not doc:
        return render_template_string(ERROR_TEMPLATE, error=f"Document {doc_id} not found.")

    # Check if already assigned
    if doc.student_id is not None:
        existing_student = session.query(Student).filter_by(id=doc.student_id).first()
        if existing_student:
            return render_template_string(
                SUCCESS_TEMPLATE,
                student_name=existing_student.name,
                file_name=doc.file_name,
                title=doc.detected_title,
            )

    # Get student
    student = session.query(Student).filter_by(id=student_id).first()
    if not student:
        return render_template_string(ERROR_TEMPLATE, error=f"Student {student_id} not found.")

    # Assign document
    doc.student_id = student.id

    # Try to match to assignment
    try:
        from scanner.matcher import AssignmentMatcher
        from scanner.parser import ParsedDocument, ParsedScore

        parsed = ParsedDocument(
            title=doc.detected_title,
            date=doc.detected_date,
        )
        if doc.detected_score is not None:
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
            logger.info(f"Matched to assignment: {match.assignment.name}")
    except Exception as e:
        logger.warning(f"Assignment matching failed: {e}")

    session.commit()

    logger.info(f"Document {doc_id} assigned to {student.name}")

    # Try to move file from Pending to Processed in Drive
    try:
        from google_services.drive_service import DriveService
        config = get_config()

        if doc.drive_file_id and config.drive.shared_folder_id:
            drive = DriveService()

            # Get the Processed folder
            processed_folder = drive.get_or_create_subfolder(
                config.drive.shared_folder_id, "Processed"
            )
            pending_folder = drive.get_or_create_subfolder(
                config.drive.shared_folder_id, "Pending"
            )

            # Move from Pending to Processed
            drive.move_file(doc.drive_file_id, processed_folder, pending_folder)
            logger.info(f"Moved {doc.file_name} to Processed folder")
    except Exception as e:
        logger.warning(f"Failed to move file: {e}")

    return render_template_string(
        SUCCESS_TEMPLATE,
        student_name=student.name,
        file_name=doc.file_name,
        title=doc.detected_title,
    )


def run_server(host="0.0.0.0", port=5000, debug=False):
    """Run the Flask development server."""
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run assignment web server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()

    print(f"Starting assignment server on http://{args.host}:{args.port}")
    print("Endpoints:")
    print(f"  GET /assign/<token>/<student_id> - Assign document to student")
    print()

    run_server(args.host, args.port, args.debug)
