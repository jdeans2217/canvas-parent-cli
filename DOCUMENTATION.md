# Canvas Parent Portal - Technical Documentation

## Overview

This project provides a CLI tool for parents to monitor their children's academic progress through the Canvas LMS API. The system uses a parent/observer account to access student data.

---

## System Architecture

### Authentication
- **API Token**: Bearer token authentication via Canvas API key
- **Account Type**: Parent Observer account
- **Permissions**: Read-only access to observed students' courses and grades

### API Base URL
```
https://yourschool.instructure.com/api/v1
```

---

## Data Inventory

### Students (Observees)

The CLI automatically discovers observed students via the `/users/self/observees` endpoint. Student IDs and course IDs are fetched dynamically at runtime.

### Example Course Types

Typical courses include:
- **Specials** - Art, Music, PE schedules
- **History** - Student books, activity pages
- **Homeroom** - Announcements, weekly updates
- **Language Arts** - Grammar, writing materials
- **Math** - Textbook PDFs, assessments
- **Reading** - Fluency checkouts, reading tests
- **Science** - Study guides, test resources

---

## API Endpoints Reference

### Working Endpoints (Tested & Verified)

| Endpoint | Purpose | Notes |
|----------|---------|-------|
| `/users/self/observees` | Get observed students | Returns student IDs and names |
| `/users/{id}/courses` | Get student's courses | Use `include[]=term` for term info |
| `/courses/{id}/assignments` | Get course assignments | Paginated, use `order_by=due_at` |
| `/courses/{id}/students/submissions` | Get student submissions | Use `student_ids[]` and `include[]=assignment` |
| `/courses/{id}/modules` | Get course modules | Use `include[]=items` for content |
| `/courses/{id}/discussion_topics` | Get discussions/announcements | Use `only_announcements=true` for announcements |
| `/courses/{id}/pages` | Get wiki pages | Weekly agenda pages |
| `/courses/{id}/files` | Get course files | PDFs, textbooks, worksheets |
| `/courses/{id}/folders` | Get file folders | Folder structure |
| `/courses/{id}/enrollments` | Get enrollments | Use for grade totals |
| `/courses/{id}/assignment_groups` | Get grading weights | Shows category weights |
| `/courses/{id}/grading_periods` | Get grading periods | Q1-Q4 dates |
| `/users/{id}/missing_submissions` | Get missing work | Cross-course missing items |
| `/conversations` | Get messages | Inbox messages |
| `/announcements` | Get announcements | Use `context_codes[]` param |

### Grading Structure Example (Math - Saxon 3)

| Category | Weight |
|----------|--------|
| Fact Assessments | 20% |
| Written Assessments | 60% |
| Homework/Classwork | 20% |

### Grading Periods (2025-2026)

| Quarter | Start | End |
|---------|-------|-----|
| Q1 | July 21, 2025 | Sept 23, 2025 |
| Q2 | Oct 13, 2025 | Dec 23, 2025 |
| Q3 | Jan 12, 2026 | Mar 17, 2026 |
| Q4 | Apr 6, 2026 | Jun 16, 2026 |

---

## Current CLI Features

### Main Menu
1. **Student Selection** - Choose from observed students

### Student Menu
1. **Quick Dashboard** - Visual grade bars, missing count, urgent items
2. **View All Grades** - Summary of current scores across all courses
3. **View All Missing Work** - Missing assignments grouped by course
4. **Browse Courses** - Detailed course exploration

### Course Menu
1. **View Grades (detailed)** - Individual assignment scores
2. **View Assignments** - Upcoming, missing, and graded assignments
3. **View Modules** - Course content structure
4. **View Announcements** - Teacher communications
5. **View Files** - Downloadable materials (PDFs, worksheets)
6. **View Pages** - Weekly agenda pages

---

## Data Not Currently Accessible

### API Limitations
1. **Syllabus content** - Returns 404 or empty via API (accessible via web only)
2. **Discussion replies** - Limited to topics, not full thread content
3. **Submission attachments** - File URLs may require session authentication
4. **Real-time notifications** - No push notification API for parents

### Permission Restrictions
1. **Other students' data** - Observer can only see linked students
2. **Teacher gradebook** - Cannot see class averages or statistics
3. **Attendance records** - Not accessible via parent API
4. **Student activity logs** - Limited access to login/page view data

---

## Improvement Opportunities

### High Priority - Core UX

#### 1. Grade Trend Tracking
**Problem**: No historical view of grades over time
**Solution**:
- Store grade snapshots daily/weekly in local SQLite database
- Add trend visualization (improving/declining)
- Show grade change indicators (+/-) since last check

```
Math - Saxon 3: 92.5% ▲+2.3% (from 90.2%)
Reading - 3:    88.1% ▼-1.2% (from 89.3%)
```

#### 2. Smart Alerts System
**Problem**: Parents must manually check for updates
**Solution**:
- Detect new assignments (due soon)
- Detect newly graded work
- Detect grade drops below threshold
- Optional email/SMS notifications

#### 3. Upcoming Due Dates View
**Problem**: No unified calendar view
**Solution**:
- Aggregate assignments across all courses
- Show next 7 days view
- Highlight overdue items prominently

```
=== NEXT 7 DAYS ===
TODAY (Dec 16):
  - Science Test: Weather and Climate (Science 3)

TOMORROW (Dec 17):
  - Invention Project Due (Reading 3)

THURSDAY (Dec 19):
  - Reading Test (Reading 3)
  - Fluency Checkout (Reading 3)
```

### Medium Priority - Enhanced Features

#### 4. Course Performance Comparison
**Problem**: Hard to identify struggling areas
**Solution**:
- Side-by-side grade comparison
- Identify courses below threshold (e.g., <85%)
- Compare against grading period averages

#### 5. Assignment Type Analysis
**Problem**: Can't see which types of work affect grades most
**Solution**:
- Break down by assignment group (tests vs homework)
- Show points earned vs points possible per category
- Identify weak areas (e.g., "Tests averaging 78%, Homework averaging 95%")

#### 6. Teacher Contact Integration
**Problem**: No quick way to contact teachers
**Solution**:
- Extract teacher emails from course info
- Add "Contact Teacher" option per course
- Pre-fill context (course name, student name)

#### 7. Module Progress Tracking
**Problem**: Can't see completion status at a glance
**Solution**:
- Show module completion percentage
- Track which items are completed vs pending
- Highlight current active module

### Lower Priority - Nice to Have

#### 8. PDF Report Generation
**Problem**: No printable progress reports
**Solution**:
- Generate weekly/monthly PDF summaries
- Include grades, missing work, announcements
- Shareable format for family members

#### 9. Multi-Student Comparison
**Problem**: Parents with multiple children can't compare progress
**Solution**:
- Side-by-side dashboard for both students
- Quick switch between students
- Unified missing work view

#### 10. Search Functionality
**Problem**: Hard to find specific assignments/announcements
**Solution**:
- Global search across all courses
- Filter by type (assignment, file, announcement)
- Date range filtering

#### 11. Offline Mode
**Problem**: Requires internet for every view
**Solution**:
- Cache recent data locally
- Show last-updated timestamp
- Refresh on demand

#### 12. Export to Calendar
**Problem**: Due dates not in parent's calendar
**Solution**:
- Export assignments to ICS format
- Integration with Google Calendar/iCal
- Sync upcoming due dates

---

## Technical Debt & Code Improvements

### Error Handling
- Add retry logic for API timeouts
- Better error messages for permission issues
- Handle API rate limiting

### Performance
- Cache student/course data (refreshed on startup)
- Parallel API calls for multiple courses
- Lazy loading for large data sets (files, modules)

### Code Structure
- Separate API layer from presentation
- Add configuration file for customization
- Implement logging for debugging

### Testing
- Add unit tests for API functions
- Mock API responses for offline testing
- Validation of data structures

---

## File Reference

### Root Directory
| File | Purpose |
|------|---------|
| `canvas_cli.py` | Main CLI tool |
| `test_api.py` | Quick API connection test |
| `site_map.json` | Complete site structure data |
| `.env` | Configuration (API keys, credentials) |
| `requirements.txt` | Python dependencies |

### tools/
| File | Purpose |
|------|---------|
| `api_explorer.py` | Interactive API endpoint testing |
| `canvas_crawler.py` | Requests-based web crawler |
| `selenium_crawler.py` | Headless browser crawler |
| `site_mapper.py` | Website structure discovery |

### experiments/
| File | Purpose |
|------|---------|
| `llm_canvas.py` | LLM-powered assistant (Ollama) |

### archive/
Old test scripts with hardcoded credentials (12 files) - kept for reference

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run CLI
python canvas_cli.py

# Generate site map
python site_mapper.py
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `CANVAS_API_URL` | Base URL (https://yourschool.instructure.com) |
| `CANVAS_API_KEY` | API bearer token |
| `CANVAS_USERNAME` | Web login email (for Selenium tools) |
| `CANVAS_PASSWORD` | Web login password (for Selenium tools) |
| `STUDENTS` | Pre-configured student IDs (optional) |

---

---

## Homework Scanner Module

### Overview
The scanner module processes photos of homework, tests, and worksheets using Mistral OCR, extracts grade information, and matches documents to Canvas assignments.

### Components

| File | Purpose |
|------|---------|
| `scanner/ocr.py` | Mistral OCR wrapper for text extraction |
| `scanner/parser.py` | Extract grades, dates, titles from OCR text |
| `scanner/matcher.py` | Match scanned docs to Canvas assignments |
| `scanner/email_processor.py` | Process homework photos from Gmail |

### Supported Formats
- **Images**: PNG, JPEG, WEBP, GIF
- **Documents**: PDF

### OCR Processing Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Image/PDF  │────►│  Mistral OCR │────►│    Parser    │────►│   Matcher    │
│              │     │              │     │              │     │              │
│ homework.jpg │     │ Extract text │     │ Find scores  │     │ Link to      │
│              │     │              │     │ Find dates   │     │ Canvas       │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

### Parser Capabilities

The grade parser extracts:
- **Scores**: `42/50`, `85%`, `Score: 90`
- **Letter Grades**: `A+`, `B-`, `Grade: C`
- **Dates**: `01/15/2024`, `January 15, 2024`, `2024-01-15`
- **Titles**: Assignment names, chapter/unit headers
- **Student Names**: From "Name:" fields
- **Course Names**: Subject identifiers

### Assignment Matching

Matching uses weighted scoring:
- **Title Similarity**: 50% (fuzzy string matching)
- **Date Proximity**: 30% (within 7 days of due date)
- **Course Name**: 20% (course name matching)

Confidence threshold: 70% for automatic matching

### Database Schema

Scanned documents are stored in the `scanned_documents` table:

```sql
scanned_documents (
  id,
  student_id,          -- FK to students
  assignment_id,       -- FK to assignments (nullable if unmatched)
  file_path,
  file_name,
  mime_type,
  scan_date,
  source,              -- 'email', 'manual', etc.
  ocr_text,
  detected_title,
  detected_date,
  detected_score,
  detected_max_score,
  canvas_score,        -- For comparison
  score_discrepancy,   -- Alerts if different
  match_confidence,
  match_method,        -- 'title', 'date', 'title+date'
  verified             -- Manual verification flag
)
```

---

## Planned: iMessage Integration

### Architecture

For users with a spare Mac, native iMessage integration enables:
- Receiving homework photos via text message
- Sending grade alerts to parents
- Two-way communication without email

```
┌─────────────────────────────────────────────────────────────────┐
│                        Mac Host (iMessage)                       │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │ Messages.app│    │ chat.db     │    │ Attachments │         │
│  │             │    │ (SQLite)    │    │ folder      │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│         │                  │                  │                  │
│         ▼                  ▼                  ▼                  │
│  ┌──────────────────────────────────────────────────────┐      │
│  │              Python iMessage Service                  │      │
│  │  - Monitor chat.db for new messages                  │      │
│  │  - Extract image attachments                         │      │
│  │  - Send messages via AppleScript                     │      │
│  │  - REST API for Linux server                         │      │
│  └──────────────────────────────────────────────────────┘      │
│                             │                                    │
└─────────────────────────────│────────────────────────────────────┘
                              │ HTTP API
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Linux Server (Main App)                      │
├─────────────────────────────────────────────────────────────────┤
│  - Canvas API integration                                        │
│  - PostgreSQL database                                           │
│  - Mistral OCR processing                                        │
│  - Report generation                                             │
│  - iMessage client (calls Mac API)                               │
└─────────────────────────────────────────────────────────────────┘
```

### Mac Service Components

| Component | Purpose |
|-----------|---------|
| `imessage/monitor.py` | Watch chat.db for incoming messages |
| `imessage/sender.py` | Send messages via AppleScript |
| `imessage/api.py` | REST API server (Flask/FastAPI) |
| `imessage/attachments.py` | Extract and process image attachments |

### Key Files on Mac

| Path | Purpose |
|------|---------|
| `~/Library/Messages/chat.db` | SQLite database of all messages |
| `~/Library/Messages/Attachments/` | Received files and images |

### AppleScript for Sending

```applescript
tell application "Messages"
    set targetService to 1st service whose service type = iMessage
    set targetBuddy to buddy "+15551234567" of targetService
    send "Grade Alert: Math score dropped to 75%" to targetBuddy
end tell
```

### Security Considerations

- Mac must grant Terminal/Python "Full Disk Access" for chat.db
- Messages app must be signed into iCloud
- API should use authentication tokens
- Consider TLS for HTTP communication

---

## Planned: SMS/Twilio Integration

### Alternative for Non-Mac Users

Twilio provides cross-platform messaging:

```python
# Example Twilio integration
from twilio.rest import Client

client = Client(account_sid, auth_token)

# Send SMS alert
message = client.messages.create(
    body="Grade Alert: JJ's Math score is now 85%",
    from_="+15551234567",  # Your Twilio number
    to="+15559876543"       # Parent's phone
)

# Receive MMS (webhook endpoint)
@app.route("/sms/incoming", methods=["POST"])
def incoming_sms():
    media_url = request.form.get("MediaUrl0")  # Homework photo
    # Process through OCR pipeline
```

### Twilio Costs (Approximate)

| Item | Cost |
|------|------|
| Phone Number | $1.15/month |
| Outbound SMS | $0.0079/message |
| Inbound SMS | $0.0075/message |
| MMS (photos) | $0.02/message |

---

## Revision History

- **2026-01-13**: Added homework scanner with Mistral OCR
- **2026-01-13**: Added planned iMessage/Twilio documentation
- **2026-01-12**: Added Google Calendar integration
- **2026-01-12**: Added Gmail email reports
- **2026-01-11**: Added PostgreSQL database and migrations
- **2026-01-05**: Initial comprehensive documentation
- **2026-01-05**: CLI tool completed with full feature set
- **2026-01-05**: Site mapping completed for both students
