# Canvas Parent CLI - Project Context

## Overview
CLI tool for parents to monitor children's academic progress via Canvas LMS API, with Google Workspace integration and homework scanning.

## Tech Stack
- **Language**: Python 3.11
- **Database**: PostgreSQL (`canvas_parent` database)
- **ORM**: SQLAlchemy + Alembic migrations
- **OCR**: Mistral AI
- **Google APIs**: Gmail, Calendar, Docs, Drive

## Project Structure
```
canvas-parent-cli/
├── canvas_cli.py          # Main CLI (interactive menu)
├── canvas_api.py          # Canvas API wrapper
├── config.py              # Centralized config from .env
├── database/              # PostgreSQL models + migrations
├── google_services/       # Gmail, Calendar integration
├── scanner/               # Mistral OCR homework processing
├── reports/               # Email report generation
└── cli/                   # CLI subcommands
```

## Key Files
| File | Purpose |
|------|---------|
| `.env` | API keys, credentials (not in git) |
| `config.py` | Loads all config from environment |
| `database/models.py` | SQLAlchemy models (students, courses, assignments, scanned_documents) |
| `scanner/ocr.py` | Mistral OCR wrapper |
| `scanner/parser.py` | Grade/date extraction from OCR text |

## Current State (as of 2026-01-13)

### Completed Features
- Core CLI with grades, assignments, modules, announcements
- PostgreSQL database with migrations
- Google OAuth authentication
- Gmail email reports with visualizations
- Google Calendar sync (per-student calendars)
- Mistral OCR homework scanner
- Email attachment processing
- Google Drive scanning integration
- Dropbox integration (code complete, see TODO below)
- Smart student detection (cover sheets, name matching)
- File hash duplicate detection

### Priority: Canvas API Exploration
Different teachers use Canvas differently - need to audit each course to capture all available data:
- Some teachers use Modules, others don't
- Grading schemes vary (weighted categories, points-based, etc.)
- Some use Announcements, others use Pages for updates
- Assignment types differ (online submission, paper, external tools)
- Some courses have rubrics, others don't
- Discussion boards usage varies
- File organization differs by teacher

**Tools for exploration:**
- `tools/api_explorer.py` - Interactive endpoint testing
- `python -c "from canvas_api import ..."` - Quick API calls
- Check each course individually for available endpoints

**Key endpoints to audit per course:**
- `/courses/{id}/modules` - Content organization
- `/courses/{id}/assignment_groups` - Grading weights
- `/courses/{id}/rubrics` - Grading criteria
- `/courses/{id}/discussion_topics` - Discussions & announcements
- `/courses/{id}/pages` - Wiki/content pages
- `/courses/{id}/external_tools` - Third-party integrations
- `/courses/{id}/tabs` - What's enabled for the course

### In Progress / Planned
- [ ] **Canvas API audit** - Explore all courses for unused data sources
- [ ] **Dropbox Full Access** - Change app permissions to access SnapScan folder
  - Current app uses "App Folder" access (limited to `Dropbox/Apps/canvas_parent/`)
  - SnapScan saves to its own folder (e.g., `Dropbox/snapscan/`) which we can't access
  - Need to: Go to Dropbox App Console → canvas_parent app → Settings → Change to "Full Dropbox"
  - Then re-authenticate with `python -m cli.process_dropbox auth`
- [ ] LLM-powered study guide generator
- [ ] Google Docs export
- [ ] Grade trend alerts
- [ ] iMessage integration (Mac host architecture documented)
- [ ] Twilio SMS (alternative to iMessage)

## Database
- **Connection**: `DATABASE_URL` in .env (PostgreSQL on localhost)
- **Tables**: students, courses, assignments, scanned_documents, grade_snapshots
- **Migrations**: Run `alembic upgrade head`

## API Keys Required
| Service | Env Variable | Purpose |
|---------|--------------|---------|
| Canvas | `CANVAS_API_KEY` | LMS data access |
| Mistral | `MISTRAL_API_KEY` | OCR processing |
| Google | `credentials.json` + `token.json` | Gmail/Calendar/Drive |
| Dropbox | `DROPBOX_APP_KEY` + `DROPBOX_APP_SECRET` | Alternative cloud storage (optional) |

## Common Commands
```bash
# Main CLI
python canvas_cli.py

# Process homework photo
python -m cli.process_scan file /path/to/image.jpg

# Process Google Drive scans
python -m cli.process_drive scan

# Process Dropbox scans (requires full access setup)
python -m cli.process_dropbox auth    # Authenticate
python -m cli.process_dropbox scan    # Process files
python -m cli.process_dropbox status  # Check config

# Send email report
python -m cli.send_report --type daily

# Sync calendar
python -m cli.sync_calendar --student "JJ"

# Run migrations
alembic upgrade head
```

## Students
- JJ Deans (Canvas ID: 13414)
- William Deans (Canvas ID: 17383)

## Notes
- Google OAuth needs proper credentials.json from Google Cloud Console
- The plan file at `.claude/plans/mossy-sprouting-snail.md` has the full implementation plan
- iMessage integration documented but not yet implemented (requires Mac host)
- **Dropbox**: Code is complete but app needs "Full Dropbox" access to read SnapScan folder (see In Progress section)
