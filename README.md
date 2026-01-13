# Canvas Parent CLI

A command-line tool for parents to monitor their children's academic progress through the Canvas LMS API, with Google Workspace integration for automated reports and notifications.

## Why This Exists

I'm not a developer by trade, just a parent who found my school's Canvas website frustrating to navigate. Getting a quick snapshot of my kids' grades and missing assignments required too many clicks and too much time. I built this tool to solve that problem for myself.

The goal is simple: fast access to the information that matters—grades, missing work, and upcoming assignments—without wading through the full Canvas interface. Now with automated email reports and the ability to scan homework photos for grade tracking.

This is a work in progress. It works for my school's Canvas setup, but your mileage may vary.

## Features

### Core Features (CLI)
- **Dashboard** - Visual grade overview with progress bars
- **Grades** - Detailed scores for all courses and assignments
- **Missing Work** - Track incomplete assignments across all courses
- **Assignments** - View upcoming, graded, and overdue work
- **Modules** - Browse course content and materials
- **Announcements** - Read teacher communications
- **Files** - Access course documents and resources

### Google Workspace Integration
- **Gmail Reports** - Automated daily/weekly email reports with grades, missing work, and visualizations
- **Google Calendar** - Sync assignment due dates to per-student calendars
- **Google Docs** - AI-generated study guides and practice problems (coming soon)

### Homework Scanner (NEW)
- **Mistral OCR** - Extract text from photos of homework, tests, and worksheets
- **Grade Parsing** - Automatically detect scores, dates, and assignment names
- **Assignment Matching** - Link scanned documents to Canvas assignments
- **Email Processing** - Send homework photos via email for automatic processing

## Installation

```bash
# Clone the repo
git clone https://github.com/jdeans2217/canvas-parent-cli.git
cd canvas-parent-cli

# Install dependencies
pip install -r requirements.txt

# Configure your credentials
cp .env.example .env
# Edit .env with your Canvas API key and other settings
```

## Configuration

### Step 1: Find Your School's Canvas URL

Your school's Canvas URL is what you see when you log in to Canvas. It typically looks like:
- `https://yourschool.instructure.com`
- `https://canvas.yourschool.edu`

Just use the base URL (no `/login` or other paths).

### Step 2: Generate an API Key

1. Log in to Canvas with your **parent/observer account**
2. Click **Account** (left sidebar) → **Settings**
3. Scroll down to **Approved Integrations**
4. Click **+ New Access Token**
5. Enter a purpose (e.g., "Parent CLI") and leave expiration blank (or set one if you prefer)
6. Click **Generate Token**
7. **Copy the token immediately** - you won't be able to see it again!

> **Note:** The API key inherits your account permissions. As a parent/observer, you'll only have read access to your linked students' data.

### Step 3: Create Your Config File

```bash
cp .env.example .env
```

Edit `.env` with your info:

```bash
# Canvas API
CANVAS_API_URL=https://yourschool.instructure.com
CANVAS_API_KEY=paste_your_token_here

# Database (PostgreSQL)
DATABASE_URL=postgresql://user:pass@localhost:5432/canvas_parent

# Mistral OCR (for homework scanning)
MISTRAL_API_KEY=your_mistral_api_key

# Email Recipients (comma-separated)
EMAIL_RECIPIENTS=parent@gmail.com,spouse@gmail.com
```

### Step 4: Set Up Database

```bash
# Run migrations
alembic upgrade head
```

### Step 5: Set Up Google OAuth (for Gmail/Calendar)

```bash
# Run the setup script
python setup_google_auth.py
```

This will guide you through Google OAuth authentication.

### Step 6: Test Your Connection

```bash
python test_api.py
```

If successful, you'll see your name and user ID. If not, double-check your URL and API key.

## Usage

### Main CLI

```bash
python canvas_cli.py
```

Navigate using the numbered menu to select students, courses, and data views.

### Email Reports

```bash
# Send a test report
python -m cli.send_report --test

# Send daily report
python -m cli.send_report --type daily
```

### Calendar Sync

```bash
# List calendars
python -m cli.sync_calendar --list

# Sync assignments for a student
python -m cli.sync_calendar --student "JJ"
```

### Homework Scanner

```bash
# Process a single image/PDF
python -m cli.process_scan file /path/to/homework.jpg

# Process with verbose output
python -m cli.process_scan file /path/to/test.png -v

# Match to Canvas assignment
python -m cli.process_scan file /path/to/test.png --match --student "JJ"

# List emails with homework attachments
python -m cli.process_scan email --list-only

# Process homework photos from email
python -m cli.process_scan email --student "JJ"
```

## Project Structure

```
canvas-parent-cli/
├── canvas_cli.py              # Main CLI application
├── canvas_api.py              # Canvas API wrapper
├── config.py                  # Centralized configuration
├── setup_google_auth.py       # Google OAuth setup script
│
├── database/                  # PostgreSQL integration
│   ├── models.py              # SQLAlchemy models
│   ├── connection.py          # DB connection handling
│   └── migrations/            # Alembic migrations
│
├── google_services/           # Google Workspace integration
│   ├── auth.py                # Shared OAuth2 handling
│   ├── gmail_service.py       # Email sending
│   └── calendar_service.py    # Calendar sync
│
├── scanner/                   # Homework scanning (NEW)
│   ├── ocr.py                 # Mistral OCR integration
│   ├── parser.py              # Grade/date extraction
│   ├── matcher.py             # Assignment matching
│   └── email_processor.py     # Gmail attachment processing
│
├── reports/                   # Report generation
│   ├── data_collector.py      # Canvas data aggregation
│   ├── report_builder.py      # Report structures
│   └── visualizations.py      # Charts and graphs
│
├── cli/                       # CLI commands
│   ├── send_report.py         # Email report command
│   ├── sync_calendar.py       # Calendar sync command
│   └── process_scan.py        # Homework scanner command
│
├── tools/                     # Development utilities
│   ├── api_explorer.py        # Test API endpoints
│   └── ...
│
└── experiments/               # Experimental features
    └── llm_canvas.py          # LLM-powered assistant
```

## Roadmap

### Completed
- [x] Core CLI with grades, assignments, modules
- [x] PostgreSQL database for grade history
- [x] Google OAuth authentication
- [x] Gmail email reports with visualizations
- [x] Google Calendar sync for due dates
- [x] Mistral OCR homework scanner
- [x] Email attachment processing

### In Progress
- [ ] LLM-powered study guide generator
- [ ] Google Docs export for study materials
- [ ] Grade trend analysis and alerts

### Planned Features

#### iMessage Integration (Requires Mac Host)
Native iMessage support for receiving homework photos and sending alerts.

**Architecture:**
```
┌─────────────────────┐         ┌─────────────────────┐
│   Mac (iMessage)    │  HTTP   │  Linux (Main App)   │
│                     │◄───────►│                     │
│ - Messages.app      │         │ - Canvas API        │
│ - Watch for photos  │         │ - PostgreSQL        │
│ - Send alerts       │         │ - Mistral OCR       │
│ - REST API server   │         │ - Reports           │
└─────────────────────┘         └─────────────────────┘
```

**Capabilities:**
- Send grade alerts via iMessage
- Receive homework photos via iMessage
- Monitor `~/Library/Messages/chat.db` for incoming messages
- Process attachments from `~/Library/Messages/Attachments/`

**Requirements:**
- Spare Mac (Mac Mini, MacBook, etc.) running as always-on server
- Python service with AppleScript integration
- REST API for communication with main Linux server

#### SMS/Twilio Integration (Alternative)
For users without a Mac, Twilio provides:
- SMS grade alerts
- MMS homework photo receiving
- Two-way messaging
- Works from any server

#### Additional Planned Features
- [ ] Google Sheets grade export
- [ ] Google Tasks for missing work
- [ ] Scheduled report automation (cron/systemd)
- [ ] Multi-student comparison dashboard
- [ ] PDF report generation
- [ ] Mobile-friendly web interface

## Canvas Implementation Notes

**Important:** Canvas is highly configurable, and different schools may have different setups. This tool was developed against a specific Canvas instance and may require adjustments for your school:

- **API endpoints** - Some endpoints may be disabled or restricted by your school's Canvas admin
- **Permissions** - Parent/observer accounts may have different access levels depending on school configuration
- **Data structure** - Course organization, grading periods, and term structures vary by institution
- **Features** - Some schools disable modules, announcements, or other features

If you encounter 403 (Forbidden) or 404 (Not Found) errors, your school's Canvas configuration may differ. Check `DOCUMENTATION.md` for the full list of endpoints used.

## Documentation

See [DOCUMENTATION.md](DOCUMENTATION.md) for:
- Complete API endpoint reference
- Data structures and grading info
- Technical details

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `CANVAS_API_URL` | Base URL (https://yourschool.instructure.com) | Yes |
| `CANVAS_API_KEY` | API bearer token | Yes |
| `DATABASE_URL` | PostgreSQL connection string | For database features |
| `MISTRAL_API_KEY` | Mistral AI API key | For homework scanning |
| `EMAIL_RECIPIENTS` | Comma-separated email addresses | For email reports |
| `GOOGLE_CREDENTIALS_FILE` | Path to OAuth credentials | For Google services |

## License

MIT
