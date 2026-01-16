#!/usr/bin/env python3
"""Run a recursive crawl of Canvas web pages."""

import os
import sys
import re
import json
import requests
from urllib.parse import urljoin, urlparse
from collections import defaultdict
from bs4 import BeautifulSoup

# Load env manually
env_path = '/home/jasondeans/learn/canvas_api/simple_tests/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key] = val.strip('"\'')

BASE_URL = os.getenv("CANVAS_API_URL")
API_KEY = os.getenv("CANVAS_API_KEY")

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {API_KEY}",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

# Storage
visited = set()
sitemap = {}
api_endpoints = set()
all_links = set()

def normalize_url(url, base):
    if not url or url.startswith(('#', 'javascript:', 'mailto:')):
        return None
    if url.startswith('//'):
        url = 'https:' + url
    full = urljoin(base, url)
    parsed = urlparse(full)
    base_parsed = urlparse(BASE_URL)
    if parsed.netloc and parsed.netloc != base_parsed.netloc:
        return None
    # Skip files
    if any(full.lower().endswith(ext) for ext in ['.pdf', '.png', '.jpg', '.css', '.js', '.ico', '.svg', '.gif', '.zip', '.doc', '.docx', '.xlsx']):
        return None
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

def crawl_page(url, depth=0, max_depth=2, course_filter=None):
    global visited, sitemap, api_endpoints, all_links

    if url in visited or depth > max_depth:
        return
    if course_filter and '/courses/' in url:
        if f'/courses/{course_filter}' not in url:
            return

    visited.add(url)
    short = url.replace(BASE_URL, '') or '/'

    try:
        resp = session.get(url, timeout=15, allow_redirects=True)
        if 'login' in resp.url and 'login' not in url:
            print(f"{'  '*depth}[REDIRECT->LOGIN] {short[:50]}")
            return
        if resp.status_code != 200:
            print(f"{'  '*depth}[{resp.status_code}] {short[:50]}")
            return
        if 'text/html' not in resp.headers.get('Content-Type', ''):
            return

        soup = BeautifulSoup(resp.text, 'lxml')
        title = soup.title.string.strip() if soup.title else 'No title'

        # Find API endpoints in scripts
        for script in soup.find_all('script'):
            text = script.string or ''
            for m in re.findall(r'/api/v1/[a-zA-Z0-9_/\-]+', text):
                api_endpoints.add(m.split('?')[0])

        # Extract links
        links = set()
        for a in soup.find_all('a', href=True):
            norm = normalize_url(a.get('href'), url)
            if norm:
                links.add(norm)
                all_links.add(norm)

        # Page type detection
        page_type = 'other'
        if '/modules' in url: page_type = 'modules'
        elif '/assignments/' in url: page_type = 'assignment_detail'
        elif '/assignments' in url: page_type = 'assignments'
        elif '/grades' in url: page_type = 'grades'
        elif '/pages/' in url: page_type = 'page_detail'
        elif '/pages' in url: page_type = 'pages'
        elif '/announcements' in url: page_type = 'announcements'
        elif '/discussion_topics' in url: page_type = 'discussions'
        elif '/files' in url: page_type = 'files'
        elif '/syllabus' in url: page_type = 'syllabus'
        elif '/quizzes' in url: page_type = 'quizzes'
        elif re.search(r'/courses/\d+$', url): page_type = 'course_home'

        sitemap[url] = {
            'title': title[:80],
            'type': page_type,
            'links': len(links),
            'depth': depth
        }

        print(f"{'  '*depth}[OK] {short[:55]:<55} | {page_type:<15} | {len(links):>3} links")

        # Recurse
        for link in sorted(links)[:20]:
            crawl_page(link, depth+1, max_depth, course_filter)

    except Exception as e:
        print(f"{'  '*depth}[ERR] {short[:40]}: {str(e)[:30]}")

def main():
    print("="*80)
    print("CANVAS RECURSIVE WEB CRAWLER")
    print("="*80)
    print(f"Target: {BASE_URL}")

    # Test auth
    resp = session.get(f"{BASE_URL}/api/v1/users/self", headers={"Accept": "application/json"})
    if resp.status_code == 200:
        print(f"Authenticated as: {resp.json().get('name')}")
    else:
        print("Auth failed!")
        return

    # Get students
    resp = session.get(f"{BASE_URL}/api/v1/users/self/observees", headers={"Accept": "application/json"})
    students = resp.json() if resp.status_code == 200 else []
    print(f"Students: {[s.get('name') for s in students]}")

    # Get courses for first student
    student_id = students[0]['id'] if students else None
    resp = session.get(f"{BASE_URL}/api/v1/users/{student_id}/courses",
                       headers={"Accept": "application/json"},
                       params={"enrollment_state": "active", "per_page": 50})
    courses = resp.json() if resp.status_code == 200 else []

    # Filter to current courses
    from datetime import datetime
    now = datetime.now()
    active_courses = []
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
            active_courses.append(c)

    print(f"Found {len(active_courses)} active courses\n")

    # Crawl each course
    for course in active_courses[:6]:  # First 6 courses
        cid = course['id']
        name = course.get('name', 'Unknown')

        print(f"\n{'='*80}")
        print(f"COURSE: {name}")
        print(f"ID: {cid}")
        print("="*80)

        # Starting points for this course
        start_pages = [
            f"{BASE_URL}/courses/{cid}",
            f"{BASE_URL}/courses/{cid}/assignments",
            f"{BASE_URL}/courses/{cid}/modules",
            f"{BASE_URL}/courses/{cid}/grades",
            f"{BASE_URL}/courses/{cid}/announcements",
            f"{BASE_URL}/courses/{cid}/pages",
            f"{BASE_URL}/courses/{cid}/discussion_topics",
        ]

        for start in start_pages:
            crawl_page(start, depth=0, max_depth=2, course_filter=cid)

    # Summary
    print(f"\n{'='*80}")
    print("CRAWL SUMMARY")
    print("="*80)
    print(f"Total pages crawled: {len(visited)}")
    print(f"Total unique links found: {len(all_links)}")
    print(f"API endpoints discovered: {len(api_endpoints)}")

    # Group by type
    by_type = defaultdict(list)
    for url, info in sitemap.items():
        by_type[info['type']].append((url.replace(BASE_URL, ''), info['title']))

    print("\nPages by type:")
    for ptype, items in sorted(by_type.items()):
        print(f"\n  {ptype.upper()} ({len(items)}):")
        for url, title in items[:8]:
            print(f"    {url[:50]:<50} | {title[:25]}")
        if len(items) > 8:
            print(f"    ... and {len(items)-8} more")

    print("\nDiscovered API endpoints in page scripts:")
    for ep in sorted(api_endpoints)[:25]:
        print(f"  {ep}")
    if len(api_endpoints) > 25:
        print(f"  ... and {len(api_endpoints)-25} more")

    # Save results
    results = {
        'pages_crawled': len(visited),
        'total_links': len(all_links),
        'sitemap': sitemap,
        'api_endpoints': sorted(api_endpoints),
        'by_type': {k: [x[0] for x in v] for k, v in by_type.items()}
    }

    output_file = '/home/jasondeans/learn/canvas_api/simple_tests/tools/crawl_results.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_file}")

if __name__ == "__main__":
    main()
