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

### In Progress / Planned
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
| Google | `credentials.json` + `token.json` | Gmail/Calendar |

## Common Commands
```bash
# Main CLI
python canvas_cli.py

# Process homework photo
python -m cli.process_scan file /path/to/image.jpg

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
