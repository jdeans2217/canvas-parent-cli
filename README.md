# Canvas Parent CLI

A command-line tool for parents to monitor their children's academic progress through the Canvas LMS API.

## Why This Exists

I'm not a developer by trade, just a parent who found my school's Canvas website frustrating to navigate. Getting a quick snapshot of my kids' grades and missing assignments required too many clicks and too much time. I built this tool to solve that problem for myself.

The goal is simple: fast access to the information that matters—grades, missing work, and upcoming assignments—without wading through the full Canvas interface. Eventually, I'd like to add automation to push notifications and alerts to me rather than having to check manually.

This is a work in progress. It works for my school's Canvas setup, but your mileage may vary.

## Features

- **Dashboard** - Visual grade overview with progress bars
- **Grades** - Detailed scores for all courses and assignments
- **Missing Work** - Track incomplete assignments across all courses
- **Assignments** - View upcoming, graded, and overdue work
- **Modules** - Browse course content and materials
- **Announcements** - Read teacher communications
- **Files** - Access course documents and resources

## Installation

```bash
# Clone the repo
git clone https://github.com/jdeans2217/canvas-parent-cli.git
cd canvas-parent-cli

# Install dependencies
pip install -r requirements.txt

# Configure your credentials
cp .env.example .env
# Edit .env with your Canvas API key
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

> **Student IDs:** You don't need to find or configure student IDs. The CLI automatically discovers all students linked to your parent/observer account.

### Step 3: Create Your Config File

```bash
cp .env.example .env
```

Edit `.env` with your info:

```
CANVAS_API_URL=https://yourschool.instructure.com
CANVAS_API_KEY=paste_your_token_here
```

### Step 4: Test Your Connection

```bash
python test_api.py
```

If successful, you'll see your name and user ID. If not, double-check your URL and API key.

## Usage

```bash
python canvas_cli.py
```

Navigate using the numbered menu to select students, courses, and data views.

## Canvas Implementation Notes

**Important:** Canvas is highly configurable, and different schools may have different setups. This tool was developed against a specific Canvas instance and may require adjustments for your school:

- **API endpoints** - Some endpoints may be disabled or restricted by your school's Canvas admin
- **Permissions** - Parent/observer accounts may have different access levels depending on school configuration
- **Data structure** - Course organization, grading periods, and term structures vary by institution
- **Features** - Some schools disable modules, announcements, or other features

If you encounter 403 (Forbidden) or 404 (Not Found) errors, your school's Canvas configuration may differ. Check `DOCUMENTATION.md` for the full list of endpoints used, and use `tools/api_explorer.py` to test which endpoints work for your instance.

## Project Structure

```
├── canvas_cli.py        # Main CLI application
├── test_api.py          # Quick API connection test
├── tools/               # Development & exploration utilities
│   ├── api_explorer.py  # Test available API endpoints
│   ├── canvas_crawler.py
│   ├── selenium_crawler.py
│   └── site_mapper.py
└── experiments/         # Experimental features
    └── llm_canvas.py    # LLM-powered assistant (Ollama)
```

## Documentation

See [DOCUMENTATION.md](DOCUMENTATION.md) for:
- Complete API endpoint reference
- Data structures and grading info
- Feature roadmap
- Technical details

## License

MIT
