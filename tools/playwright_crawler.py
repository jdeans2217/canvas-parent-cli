#!/usr/bin/env python3
"""
Canvas SPA Crawler using Playwright
Crawls rendered Canvas pages using a headless browser.
"""

import os
import json
import re
from urllib.parse import urljoin, urlparse
from collections import defaultdict
from playwright.sync_api import sync_playwright

# Load env
env_path = '/home/jasondeans/learn/canvas_api/simple_tests/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key] = val.strip('"\'')

BASE_URL = os.environ.get("CANVAS_API_URL")
API_KEY = os.environ.get("CANVAS_API_KEY")


class CanvasSPACrawler:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key
        self.visited = set()
        self.sitemap = {}
        self.api_calls = set()
        self.all_links = set()

    def normalize_url(self, url):
        """Normalize and validate URL."""
        if not url:
            return None
        if url.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
            return None
        if url.startswith('//'):
            url = 'https:' + url

        full = urljoin(self.base_url, url)
        parsed = urlparse(full)
        base_parsed = urlparse(self.base_url)

        # Only same domain
        if parsed.netloc and parsed.netloc != base_parsed.netloc:
            return None

        # Skip files
        skip_ext = ['.pdf', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.css', '.js',
                   '.ico', '.woff', '.woff2', '.ttf', '.zip', '.doc', '.docx', '.xlsx']
        if any(parsed.path.lower().endswith(ext) for ext in skip_ext):
            return None

        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    def get_page_type(self, url):
        """Determine page type from URL."""
        path = urlparse(url).path
        if '/modules' in path: return 'modules'
        elif '/assignments/' in path: return 'assignment_detail'
        elif '/assignments' in path: return 'assignments'
        elif '/grades' in path: return 'grades'
        elif '/pages/' in path: return 'page_detail'
        elif '/pages' in path: return 'pages'
        elif '/announcements' in path: return 'announcements'
        elif '/discussion_topics/' in path: return 'discussion_detail'
        elif '/discussion_topics' in path: return 'discussions'
        elif '/files' in path: return 'files'
        elif '/syllabus' in path: return 'syllabus'
        elif '/quizzes' in path: return 'quizzes'
        elif re.search(r'/courses/\d+$', path): return 'course_home'
        elif '/calendar' in path: return 'calendar'
        elif '/inbox' in path or '/conversations' in path: return 'inbox'
        elif '/profile' in path: return 'profile'
        return 'other'

    def crawl_page(self, page, url, depth=0, max_depth=2, course_filter=None):
        """Crawl a single page and extract links."""
        if url in self.visited or depth > max_depth:
            return

        # Filter to specific course if set
        if course_filter and '/courses/' in url:
            if f'/courses/{course_filter}' not in url:
                return

        self.visited.add(url)
        short_url = url.replace(self.base_url, '') or '/'

        try:
            # Navigate to page
            response = page.goto(url, wait_until='networkidle', timeout=30000)

            if not response:
                print(f"{'  '*depth}[NO RESPONSE] {short_url[:50]}")
                return

            if response.status != 200:
                print(f"{'  '*depth}[{response.status}] {short_url[:50]}")
                return

            # Wait a bit more for dynamic content
            page.wait_for_timeout(1000)

            # Get page title
            title = page.title() or 'No title'

            # Extract all links from rendered DOM
            links = set()
            link_elements = page.query_selector_all('a[href]')
            for elem in link_elements:
                href = elem.get_attribute('href')
                norm = self.normalize_url(href)
                if norm:
                    links.add(norm)
                    self.all_links.add(norm)

            # Also check for data-href and other attributes
            for attr in ['data-href', 'data-url']:
                elements = page.query_selector_all(f'[{attr}]')
                for elem in elements:
                    href = elem.get_attribute(attr)
                    norm = self.normalize_url(href)
                    if norm:
                        links.add(norm)
                        self.all_links.add(norm)

            page_type = self.get_page_type(url)

            # Get main content text preview
            content_preview = ""
            main_content = page.query_selector('main, #content, .ic-Layout-contentMain, [role="main"]')
            if main_content:
                content_preview = main_content.inner_text()[:500]

            self.sitemap[url] = {
                'title': title[:100],
                'type': page_type,
                'links_count': len(links),
                'depth': depth,
                'content_preview': content_preview[:200]
            }

            print(f"{'  '*depth}[OK] {short_url[:50]:<50} | {page_type:<18} | {len(links):>3} links")

            # Recursively crawl found links
            for link in sorted(links)[:25]:  # Limit per page
                self.crawl_page(page, link, depth+1, max_depth, course_filter)

        except Exception as e:
            print(f"{'  '*depth}[ERR] {short_url[:40]}: {str(e)[:40]}")

    def intercept_api_calls(self, route):
        """Intercept API calls to discover endpoints."""
        url = route.request.url
        if '/api/v1/' in url:
            # Extract just the endpoint path
            parsed = urlparse(url)
            endpoint = parsed.path
            self.api_calls.add(endpoint)
        route.continue_()

    def crawl_course(self, browser, course_id, course_name, max_depth=2):
        """Crawl a single course."""
        print(f"\n{'='*80}")
        print(f"COURSE: {course_name}")
        print(f"ID: {course_id}")
        print("="*80)

        # Create context with API token cookie
        context = browser.new_context()

        # Set auth header via route interception
        def add_auth(route):
            headers = route.request.headers.copy()
            headers['Authorization'] = f'Bearer {self.api_key}'
            route.continue_(headers=headers)

        # Also intercept to log API calls
        context.route('**/*', self.intercept_api_calls)

        page = context.new_page()

        # Set auth via localStorage/cookie approach
        page.goto(self.base_url)
        page.evaluate(f'''() => {{
            localStorage.setItem('canvas_api_token', '{self.api_key}');
        }}''')

        # Add auth cookie
        context.add_cookies([{
            'name': 'canvas_session',
            'value': self.api_key,
            'domain': urlparse(self.base_url).netloc,
            'path': '/'
        }])

        # Course starting points
        start_pages = [
            f"{self.base_url}/courses/{course_id}",
            f"{self.base_url}/courses/{course_id}/modules",
            f"{self.base_url}/courses/{course_id}/assignments",
            f"{self.base_url}/courses/{course_id}/grades",
            f"{self.base_url}/courses/{course_id}/pages",
            f"{self.base_url}/courses/{course_id}/announcements",
            f"{self.base_url}/courses/{course_id}/discussion_topics",
        ]

        for start_url in start_pages:
            self.crawl_page(page, start_url, depth=0, max_depth=max_depth, course_filter=course_id)

        context.close()

    def print_summary(self):
        """Print crawl summary."""
        print(f"\n{'='*80}")
        print("CRAWL SUMMARY")
        print("="*80)

        print(f"Total pages crawled: {len(self.visited)}")
        print(f"Total unique links found: {len(self.all_links)}")
        print(f"API endpoints discovered: {len(self.api_calls)}")

        # Group by type
        by_type = defaultdict(list)
        for url, info in self.sitemap.items():
            by_type[info['type']].append((url.replace(self.base_url, ''), info['title']))

        print("\nPages by type:")
        for ptype, items in sorted(by_type.items()):
            print(f"\n  {ptype.upper()} ({len(items)}):")
            for url, title in items[:10]:
                print(f"    {url[:55]:<55} | {title[:20]}")
            if len(items) > 10:
                print(f"    ... and {len(items)-10} more")

        print("\nAPI endpoints discovered:")
        for ep in sorted(self.api_calls)[:30]:
            print(f"  {ep}")
        if len(self.api_calls) > 30:
            print(f"  ... and {len(self.api_calls)-30} more")


def get_student_courses():
    """Get courses via API."""
    import requests

    session = requests.Session()
    session.headers['Authorization'] = f'Bearer {API_KEY}'

    # Get students
    resp = session.get(f"{BASE_URL}/api/v1/users/self/observees")
    students = resp.json() if resp.ok else []

    if not students:
        return []

    student_id = students[0]['id']

    # Get courses
    resp = session.get(
        f"{BASE_URL}/api/v1/users/{student_id}/courses",
        params={"enrollment_state": "active", "per_page": 50}
    )
    courses = resp.json() if resp.ok else []

    # Filter current
    from datetime import datetime
    now = datetime.now()
    active = []
    for c in courses:
        term = c.get('term', {})
        end = term.get('end_at')
        if end:
            try:
                end_dt = datetime.strptime(end, "%Y-%m-%dT%H:%M:%SZ")
                if end_dt < now:
                    continue
            except:
                pass
        if not c.get('concluded', False):
            active.append(c)

    return active, students[0]['name']


def main():
    print("="*80)
    print("CANVAS SPA CRAWLER (Playwright)")
    print("="*80)
    print(f"Target: {BASE_URL}")

    courses, student_name = get_student_courses()
    print(f"Student: {student_name}")
    print(f"Found {len(courses)} active courses")

    crawler = CanvasSPACrawler(BASE_URL, API_KEY)

    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)

        # Crawl each course
        for course in courses[:4]:  # First 4 courses
            crawler.crawl_course(
                browser,
                course['id'],
                course.get('name', 'Unknown'),
                max_depth=2
            )

        browser.close()

    crawler.print_summary()

    # Save results
    results = {
        'pages_crawled': len(crawler.visited),
        'total_links': len(crawler.all_links),
        'sitemap': crawler.sitemap,
        'api_endpoints': sorted(crawler.api_calls),
        'by_type': {}
    }

    by_type = defaultdict(list)
    for url, info in crawler.sitemap.items():
        by_type[info['type']].append(url.replace(BASE_URL, ''))
    results['by_type'] = dict(by_type)

    output_file = '/home/jasondeans/learn/canvas_api/simple_tests/tools/spa_crawl_results.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_file}")


if __name__ == "__main__":
    main()
