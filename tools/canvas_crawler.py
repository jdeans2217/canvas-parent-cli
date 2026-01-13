#!/usr/bin/env python3
"""
Canvas Website Crawler - Discover pages, data, and API endpoints
Uses API token authentication for both API and web access
"""

import os
import re
import json
import requests
from urllib.parse import urljoin, urlparse
from collections import defaultdict
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("CANVAS_API_URL", "https://yourschool.instructure.com")
API_KEY = os.getenv("CANVAS_API_KEY")

# Session with API token auth
session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {API_KEY}",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})


class CanvasCrawler:
    def __init__(self, base_url):
        self.base_url = base_url
        self.visited = set()
        self.pages = {}
        self.api_endpoints = set()
        self.interesting_data = []
        self.all_links = set()

    def normalize_url(self, url):
        if url.startswith("//"):
            url = "https:" + url
        return urljoin(self.base_url, url)

    def is_same_domain(self, url):
        parsed = urlparse(url)
        base_parsed = urlparse(self.base_url)
        return parsed.netloc == "" or parsed.netloc == base_parsed.netloc

    def extract_api_endpoints(self, text):
        patterns = [r'/api/v1/[a-zA-Z0-9_/\-]+']
        endpoints = set()
        for pattern in patterns:
            for m in re.findall(pattern, text):
                endpoints.add(m.split("?")[0])
        return endpoints

    def extract_page_data(self, soup, url):
        """Extract all useful data from page."""
        data = {
            "url": url,
            "title": soup.title.string.strip() if soup.title else "",
            "tables": [],
            "grades": [],
            "assignments": [],
            "links": [],
        }

        # Extract all links
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True)[:50]
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                full_url = self.normalize_url(href)
                if self.is_same_domain(full_url):
                    data["links"].append({"url": full_url, "text": text})
                    self.all_links.add(full_url)

        # Extract tables
        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True) for th in table.find_all("th")]
            rows = []
            for tr in table.find_all("tr")[:10]:
                cells = [td.get_text(strip=True)[:100] for td in tr.find_all(["td", "th"])]
                if cells and any(c for c in cells):
                    rows.append(cells)
            if rows:
                data["tables"].append({"headers": headers, "rows": rows})

        # Extract grade elements
        for elem in soup.find_all(class_=re.compile(r"grade|score|points", re.I)):
            text = elem.get_text(strip=True)[:150]
            if text and len(text) > 2:
                data["grades"].append(text)

        # Extract assignment elements
        for elem in soup.find_all(class_=re.compile(r"assignment|submission|due", re.I)):
            text = elem.get_text(strip=True)[:150]
            if text and len(text) > 2:
                data["assignments"].append(text)

        # Extract from scripts
        for script in soup.find_all("script"):
            script_text = script.string or ""
            self.api_endpoints.update(self.extract_api_endpoints(script_text))

        return data

    def crawl_page(self, url, depth=0, max_depth=2):
        if url in self.visited or depth > max_depth:
            return None

        # Skip static files
        if any(url.endswith(ext) for ext in ['.pdf', '.png', '.jpg', '.css', '.js', '.ico', '.svg']):
            return None

        self.visited.add(url)
        short_url = url.replace(self.base_url, "") or "/"
        print(f"{'  ' * depth}[{len(self.visited)}] {short_url}")

        try:
            resp = session.get(url, timeout=15, allow_redirects=True)

            # Check for login redirect
            if "login" in resp.url and "login" not in url:
                print(f"{'  ' * depth}    -> Redirected to login")
                return None

            if resp.status_code != 200:
                print(f"{'  ' * depth}    -> {resp.status_code}")
                return None

            content_type = resp.headers.get('Content-Type', '')
            if 'text/html' not in content_type:
                return None

            soup = BeautifulSoup(resp.text, 'lxml')
            data = self.extract_page_data(soup, url)
            self.pages[url] = data

            # Track interesting pages
            if data["tables"] or data["grades"] or data["assignments"]:
                self.interesting_data.append({
                    "url": short_url,
                    "title": data["title"],
                    "tables": len(data["tables"]),
                    "grades": len(data["grades"]),
                    "assignments": len(data["assignments"]),
                })

            # Follow links
            for link_info in data["links"][:20]:
                link = link_info["url"]
                if link not in self.visited:
                    self.crawl_page(link, depth + 1, max_depth)

            return data

        except Exception as e:
            print(f"{'  ' * depth}    Error: {str(e)[:60]}")
            return None

    def print_summary(self):
        print("\n" + "=" * 70)
        print("CRAWL SUMMARY")
        print("=" * 70)

        print(f"\nPages crawled: {len(self.visited)}")
        print(f"Total links found: {len(self.all_links)}")
        print(f"API endpoints discovered: {len(self.api_endpoints)}")

        if self.api_endpoints:
            print("\nAPI Endpoints:")
            for ep in sorted(self.api_endpoints)[:40]:
                print(f"  {ep}")

        if self.interesting_data:
            print("\nPages with Data:")
            for item in self.interesting_data[:30]:
                print(f"\n  {item['url']}")
                if item['title']:
                    print(f"    Title: {item['title'][:60]}")
                if item['tables']:
                    print(f"    Tables: {item['tables']}")
                if item['grades']:
                    print(f"    Grade elements: {item['grades']}")
                if item['assignments']:
                    print(f"    Assignment elements: {item['assignments']}")

        # Show actual table data
        print("\n" + "=" * 70)
        print("TABLE DATA FOUND")
        print("=" * 70)
        for url, data in self.pages.items():
            if data.get("tables"):
                short_url = url.replace(self.base_url, "")
                print(f"\n{short_url}:")
                for i, table in enumerate(data["tables"][:3]):
                    if table.get("headers"):
                        print(f"  Headers: {table['headers'][:6]}")
                    for row in table.get("rows", [])[:5]:
                        print(f"  Row: {row[:6]}")


def test_api_with_session():
    """Test that API access works with our session."""
    print("Testing API access...")
    resp = session.get(f"{BASE_URL}/api/v1/users/self",
                       headers={"Accept": "application/json"})
    if resp.status_code == 200:
        user = resp.json()
        print(f"Logged in as: {user.get('name')} (ID: {user.get('id')})")
        return True
    print(f"API test failed: {resp.status_code}")
    return False


def get_courses():
    """Get list of courses."""
    resp = session.get(f"{BASE_URL}/api/v1/users/self/courses",
                       headers={"Accept": "application/json"},
                       params={"enrollment_state": "active", "per_page": 50})
    if resp.status_code == 200:
        return resp.json()
    return []


def get_students():
    """Get observed students."""
    resp = session.get(f"{BASE_URL}/api/v1/users/self/observees",
                       headers={"Accept": "application/json"})
    if resp.status_code == 200:
        return resp.json()
    return []


def main():
    print("=" * 70)
    print("CANVAS CRAWLER")
    print("=" * 70)

    if not test_api_with_session():
        print("Failed to authenticate")
        return

    students = get_students()
    courses = get_courses()

    print(f"\nStudents: {[s.get('name') for s in students]}")
    print(f"Courses: {len(courses)}")

    crawler = CanvasCrawler(BASE_URL)

    print("\nOptions:")
    print("  1. Crawl main pages")
    print("  2. Crawl all grades pages")
    print("  3. Crawl specific course")
    print("  4. Crawl student grades")
    print("  5. Test specific URL")
    print("  6. Full API endpoint scan")
    print("  0. Exit")

    while True:
        choice = input("\nChoice: ").strip()

        if choice == "0":
            break

        elif choice == "1":
            pages = ["/dashboard", "/grades", "/courses", "/calendar", "/profile"]
            for p in pages:
                crawler.crawl_page(f"{BASE_URL}{p}", max_depth=1)
            crawler.print_summary()

        elif choice == "2":
            print(f"\nCrawling grades for {len(courses)} courses...")
            for course in courses:
                cid = course.get("id")
                name = course.get("name", "Unknown")[:40]
                print(f"\n--- {name} ---")
                crawler.crawl_page(f"{BASE_URL}/courses/{cid}/grades", max_depth=1)
            crawler.print_summary()

        elif choice == "3":
            print("\nCourses:")
            for i, c in enumerate(courses[:20], 1):
                print(f"  {i}. {c.get('name')}")
            sel = input("Select: ").strip()
            try:
                course = courses[int(sel) - 1]
                cid = course.get("id")
                pages = [
                    f"/courses/{cid}",
                    f"/courses/{cid}/assignments",
                    f"/courses/{cid}/grades",
                    f"/courses/{cid}/modules",
                    f"/courses/{cid}/announcements",
                    f"/courses/{cid}/discussion_topics",
                    f"/courses/{cid}/pages",
                    f"/courses/{cid}/files",
                ]
                for p in pages:
                    crawler.crawl_page(f"{BASE_URL}{p}", max_depth=1)
                crawler.print_summary()
            except:
                print("Invalid")

        elif choice == "4":
            print("\nStudents:")
            for i, s in enumerate(students, 1):
                print(f"  {i}. {s.get('name')} (ID: {s.get('id')})")
            sel = input("Select: ").strip()
            try:
                student = students[int(sel) - 1]
                sid = student.get("id")
                # Get this student's courses and grades
                for course in courses[:10]:
                    cid = course.get("id")
                    crawler.crawl_page(f"{BASE_URL}/courses/{cid}/grades/{sid}", max_depth=0)
                crawler.print_summary()
            except:
                print("Invalid")

        elif choice == "5":
            url = input("URL path (e.g., /courses/123/grades): ").strip()
            if url:
                crawler.crawl_page(f"{BASE_URL}{url}", max_depth=2)
                crawler.print_summary()

        elif choice == "6":
            # Comprehensive API scan
            print("\nScanning API endpoints...")
            from api_explorer import ENDPOINTS, COURSE_ENDPOINTS, test_endpoint

            for category, endpoints in ENDPOINTS.items():
                print(f"\n{category}:")
                for ep, desc in endpoints:
                    result = test_endpoint(ep)
                    if result["status"] == "OK":
                        print(f"  [OK] {ep}")
                        crawler.api_endpoints.add(ep)

            # Course endpoints for first few courses
            for course in courses[:3]:
                cid = course.get("id")
                print(f"\nCourse {cid}:")
                for ep_template, desc in COURSE_ENDPOINTS:
                    ep = ep_template.format(course_id=cid)
                    result = test_endpoint(ep)
                    if result["status"] == "OK":
                        print(f"  [OK] {ep}")
                        crawler.api_endpoints.add(ep_template)

            crawler.print_summary()


if __name__ == "__main__":
    main()
