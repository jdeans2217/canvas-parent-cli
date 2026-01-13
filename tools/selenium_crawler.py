#!/usr/bin/env python3
"""
Canvas Selenium Crawler - Use headless browser to discover all website data
"""

import os
import re
import time
import json
from collections import defaultdict
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

BASE_URL = os.getenv("CANVAS_API_URL", "https://yourschool.instructure.com")
USERNAME = os.getenv("CANVAS_USERNAME")
PASSWORD = os.getenv("CANVAS_PASSWORD")


class SeleniumCrawler:
    def __init__(self, headless=True):
        self.base_url = BASE_URL
        self.visited = set()
        self.pages_data = {}
        self.all_links = set()
        self.api_calls = set()

        # Setup Chrome
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")

        # Enable network logging to capture API calls
        chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10)

    def login(self):
        """Login to Canvas."""
        print("Logging in to Canvas...")
        self.driver.get(f"{self.base_url}/login/canvas")
        time.sleep(3)

        try:
            # Wait for and fill username using explicit wait for clickable
            username_field = self.wait.until(
                EC.element_to_be_clickable((By.ID, "pseudonym_session_unique_id"))
            )
            username_field.click()
            username_field.clear()
            username_field.send_keys(USERNAME)

            # Fill password
            password_field = self.wait.until(
                EC.element_to_be_clickable((By.ID, "pseudonym_session_password"))
            )
            password_field.click()
            password_field.clear()
            password_field.send_keys(PASSWORD)

            # Submit using the input submit button
            submit_button = self.driver.find_element(By.CSS_SELECTOR, "input[type='submit']")
            submit_button.click()

            # Wait for navigation
            time.sleep(4)

            current_url = self.driver.current_url
            print(f"After login URL: {current_url}")

            if "dashboard" in current_url or "login" not in current_url:
                print("Login successful!")
                return True
            else:
                print(f"Login may have failed. Checking page content...")
                if "Invalid" in self.driver.page_source or "incorrect" in self.driver.page_source:
                    print("Invalid credentials")
                    return False
                return True

        except Exception as e:
            print(f"Login error: {e}")
            # Try to continue anyway
            return True

    def extract_page_data(self, url):
        """Extract all data from current page."""
        data = {
            "url": url,
            "title": self.driver.title,
            "links": [],
            "tables": [],
            "grade_data": [],
            "assignment_data": [],
            "text_content": [],
        }

        # Get all links
        links = self.driver.find_elements(By.TAG_NAME, "a")
        for link in links:
            try:
                href = link.get_attribute("href")
                text = link.text.strip()[:50]
                if href and href.startswith(self.base_url):
                    data["links"].append({"url": href, "text": text})
                    self.all_links.add(href)
            except:
                pass

        # Get tables
        tables = self.driver.find_elements(By.TAG_NAME, "table")
        for table in tables:
            try:
                headers = [th.text.strip() for th in table.find_elements(By.TAG_NAME, "th")]
                rows = []
                for tr in table.find_elements(By.TAG_NAME, "tr")[:15]:
                    cells = [td.text.strip()[:100] for td in tr.find_elements(By.TAG_NAME, "td")]
                    if cells:
                        rows.append(cells)
                if headers or rows:
                    data["tables"].append({"headers": headers, "rows": rows})
            except:
                pass

        # Look for grade-related elements
        grade_selectors = [
            ".grade", ".score", ".points", ".student_grade",
            "[class*='grade']", "[class*='score']", "[class*='points']",
            "#grades_summary", ".final_grade", ".assignment_score"
        ]
        for selector in grade_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in elements[:20]:
                    text = elem.text.strip()[:200]
                    if text and len(text) > 1:
                        data["grade_data"].append(text)
            except:
                pass

        # Look for assignment elements
        assignment_selectors = [
            ".assignment", ".submission", "[class*='assignment']",
            ".ig-row", ".assignment-group"
        ]
        for selector in assignment_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in elements[:20]:
                    text = elem.text.strip()[:200]
                    if text and len(text) > 5:
                        data["assignment_data"].append(text)
            except:
                pass

        # Get main content text
        try:
            main = self.driver.find_element(By.ID, "content")
            data["text_content"].append(main.text[:2000])
        except:
            pass

        return data

    def capture_network_calls(self):
        """Capture API calls from network logs."""
        try:
            logs = self.driver.get_log("performance")
            for entry in logs:
                try:
                    message = json.loads(entry["message"])["message"]
                    if message["method"] == "Network.requestWillBeSent":
                        url = message["params"]["request"]["url"]
                        if "/api/v1/" in url:
                            # Clean up URL
                            api_path = re.search(r'/api/v1/[^\s\?]+', url)
                            if api_path:
                                self.api_calls.add(api_path.group())
                except:
                    pass
        except:
            pass

    def crawl_page(self, url, depth=0, max_depth=1):
        """Crawl a single page."""
        if url in self.visited or depth > max_depth:
            return

        # Skip non-canvas URLs and static files
        if not url.startswith(self.base_url):
            return
        if any(url.endswith(ext) for ext in ['.pdf', '.png', '.jpg', '.css', '.js', '.zip']):
            return

        self.visited.add(url)
        short_url = url.replace(self.base_url, "") or "/"
        print(f"{'  ' * depth}[{len(self.visited)}] {short_url}")

        try:
            self.driver.get(url)
            time.sleep(2)  # Wait for JS to render

            # Check if redirected to login
            if "login" in self.driver.current_url and "login" not in url:
                print(f"{'  ' * depth}    -> Redirected to login")
                return

            # Capture network calls
            self.capture_network_calls()

            # Extract data
            data = self.extract_page_data(url)
            self.pages_data[url] = data

            # Follow links
            for link_info in data["links"][:10]:
                link = link_info["url"]
                self.crawl_page(link, depth + 1, max_depth)

        except Exception as e:
            print(f"{'  ' * depth}    Error: {str(e)[:50]}")

    def print_summary(self):
        """Print crawl summary."""
        print("\n" + "=" * 70)
        print("CRAWL SUMMARY")
        print("=" * 70)

        print(f"\nPages visited: {len(self.visited)}")
        print(f"Total links found: {len(self.all_links)}")
        print(f"API calls captured: {len(self.api_calls)}")

        if self.api_calls:
            print("\nAPI Endpoints Used by Website:")
            for api in sorted(self.api_calls):
                print(f"  {api}")

        print("\n" + "=" * 70)
        print("PAGES WITH DATA")
        print("=" * 70)

        for url, data in self.pages_data.items():
            short_url = url.replace(self.base_url, "")
            has_data = data.get("tables") or data.get("grade_data") or data.get("assignment_data")

            if has_data:
                print(f"\n{short_url}")
                print(f"  Title: {data.get('title', 'N/A')[:60]}")

                if data.get("tables"):
                    print(f"  Tables: {len(data['tables'])}")
                    for table in data["tables"][:2]:
                        if table.get("headers"):
                            print(f"    Headers: {table['headers'][:5]}")
                        for row in table.get("rows", [])[:3]:
                            print(f"    Row: {row[:5]}")

                if data.get("grade_data"):
                    print(f"  Grade elements: {len(data['grade_data'])}")
                    for g in data["grade_data"][:5]:
                        print(f"    - {g[:80]}")

                if data.get("assignment_data"):
                    print(f"  Assignment elements: {len(data['assignment_data'])}")

    def close(self):
        """Close browser."""
        self.driver.quit()


def main():
    print("=" * 70)
    print("CANVAS SELENIUM CRAWLER")
    print("=" * 70)

    crawler = SeleniumCrawler(headless=True)

    try:
        if not crawler.login():
            print("Login failed")
            return

        print("\nOptions:")
        print("  1. Crawl main pages (dashboard, grades, courses)")
        print("  2. Crawl all course grade pages")
        print("  3. Crawl specific URL")
        print("  4. Full site crawl")
        print("  0. Exit")

        while True:
            choice = input("\nChoice: ").strip()

            if choice == "0":
                break

            elif choice == "1":
                pages = [
                    "/dashboard",
                    "/grades",
                    "/courses",
                    "/calendar",
                    "/profile",
                    "/conversations",
                ]
                for p in pages:
                    crawler.crawl_page(f"{BASE_URL}{p}", max_depth=1)
                crawler.print_summary()

            elif choice == "2":
                # Get courses first
                crawler.driver.get(f"{BASE_URL}/courses")
                time.sleep(2)

                # Find course links
                course_links = crawler.driver.find_elements(By.CSS_SELECTOR, "a[href*='/courses/']")
                course_urls = set()
                for link in course_links:
                    href = link.get_attribute("href")
                    if href and "/courses/" in href and href.endswith(tuple("0123456789")):
                        course_urls.add(href)

                print(f"Found {len(course_urls)} courses")

                for course_url in list(course_urls)[:15]:
                    # Crawl grades page for each course
                    grades_url = f"{course_url}/grades"
                    crawler.crawl_page(grades_url, max_depth=0)

                    # Also get assignments
                    assignments_url = f"{course_url}/assignments"
                    crawler.crawl_page(assignments_url, max_depth=0)

                crawler.print_summary()

            elif choice == "3":
                url = input("Enter URL path (e.g., /courses/123/grades): ").strip()
                if url:
                    crawler.crawl_page(f"{BASE_URL}{url}", max_depth=2)
                    crawler.print_summary()

            elif choice == "4":
                print("Starting full crawl from dashboard...")
                crawler.crawl_page(f"{BASE_URL}/dashboard", max_depth=2)
                crawler.print_summary()

    finally:
        crawler.close()


if __name__ == "__main__":
    main()
