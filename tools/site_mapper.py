#!/usr/bin/env python3
"""
Canvas Site Mapper - Build comprehensive navigation tree of all available data
"""

import os
import re
import time
import json
from datetime import datetime
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

BASE_URL = os.getenv("CANVAS_API_URL", "https://yourschool.instructure.com")
USERNAME = os.getenv("CANVAS_USERNAME")
PASSWORD = os.getenv("CANVAS_PASSWORD")


class CanvasSiteMapper:
    def __init__(self, headless=True):
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10)
        self.site_map = {}

    def login(self):
        print("Logging in...")
        self.driver.get(f"{BASE_URL}/login/canvas")
        time.sleep(2)
        self.driver.find_element(By.ID, "pseudonym_session_unique_id").send_keys(USERNAME)
        self.driver.find_element(By.ID, "pseudonym_session_password").send_keys(PASSWORD)
        self.driver.find_element(By.CSS_SELECTOR, "input[type='submit']").click()
        time.sleep(3)
        success = "login_success" in self.driver.current_url or "dashboard" in self.driver.current_url
        if success:
            print("Login successful!")
        return success

    def get_page_content(self, url):
        """Get content summary from a page."""
        self.driver.get(url)
        time.sleep(1.5)

        result = {
            "url": url,
            "title": self.driver.title,
            "accessible": True,
            "items": [],
            "count": 0,
        }

        body = self.driver.find_element(By.TAG_NAME, "body").text

        # Check for access issues
        if any(x in body.lower() for x in ["not found", "disabled for this course", "access denied", "not authorized"]):
            result["accessible"] = False
            return result

        if "login" in self.driver.current_url and "login" not in url:
            result["accessible"] = False
            return result

        # Count items based on page type
        try:
            content = self.driver.find_element(By.ID, "content")
            result["preview"] = content.text[:500]
        except:
            result["preview"] = body[:500]

        return result

    def get_students(self):
        """Get list of observed students."""
        print("\nFetching students...")
        self.driver.get(f"{BASE_URL}/api/v1/users/self/observees")
        time.sleep(1)
        try:
            data = json.loads(self.driver.find_element(By.TAG_NAME, "body").text)
            students = [{"id": s["id"], "name": s["name"]} for s in data]
            print(f"Found {len(students)} students")
            return students
        except:
            return []

    def get_student_courses(self, student_id, student_name):
        """Get all courses for a student."""
        print(f"\nFetching courses for {student_name}...")
        self.driver.get(f"{BASE_URL}/api/v1/users/{student_id}/courses?per_page=100&include[]=term")
        time.sleep(1)
        try:
            data = json.loads(self.driver.find_element(By.TAG_NAME, "body").text)
            courses = []
            for c in data:
                term = c.get("term", {}).get("name", "Unknown")
                courses.append({
                    "id": c["id"],
                    "name": c.get("name", "Unknown"),
                    "term": term,
                    "concluded": c.get("concluded", False),
                })
            print(f"Found {len(courses)} courses")
            return courses
        except:
            return []

    def map_course_sections(self, course_id, course_name):
        """Map all available sections in a course."""
        sections = {
            "home": {"path": "", "name": "Home"},
            "announcements": {"path": "/announcements", "name": "Announcements"},
            "assignments": {"path": "/assignments", "name": "Assignments"},
            "grades": {"path": "/grades", "name": "Grades"},
            "modules": {"path": "/modules", "name": "Modules"},
            "pages": {"path": "/pages", "name": "Pages"},
            "files": {"path": "/files", "name": "Files"},
            "syllabus": {"path": "/syllabus", "name": "Syllabus"},
            "discussions": {"path": "/discussion_topics", "name": "Discussions"},
            "quizzes": {"path": "/quizzes", "name": "Quizzes"},
        }

        course_map = {
            "id": course_id,
            "name": course_name,
            "sections": {},
        }

        for key, section in sections.items():
            url = f"{BASE_URL}/courses/{course_id}{section['path']}"
            result = self.get_page_content(url)

            if result["accessible"]:
                # Get item counts
                items = self.driver.find_elements(By.CSS_SELECTOR,
                    ".ig-row, .assignment, .discussion-topic, .wiki-page-link, .context_module_item, .announcement")

                course_map["sections"][key] = {
                    "name": section["name"],
                    "url": url,
                    "item_count": len(items),
                    "preview": result.get("preview", "")[:200],
                }

        return course_map

    def build_full_site_map(self):
        """Build complete site map for all students."""
        site_map = {
            "generated": datetime.now().isoformat(),
            "students": [],
        }

        students = self.get_students()

        for student in students:
            print(f"\n{'='*60}")
            print(f"MAPPING: {student['name']}")
            print("=" * 60)

            student_map = {
                "id": student["id"],
                "name": student["name"],
                "courses": {"current": [], "past": []},
            }

            courses = self.get_student_courses(student["id"], student["name"])

            # Separate current vs past courses
            for course in courses:
                is_current = "2025" in course["term"] or "2024/2025" in course["term"]

                if is_current and not course["concluded"]:
                    print(f"\n  Mapping: {course['name']}")
                    course_map = self.map_course_sections(course["id"], course["name"])
                    course_map["term"] = course["term"]
                    student_map["courses"]["current"].append(course_map)

                    # Show what was found
                    available = [s for s, d in course_map["sections"].items() if d.get("item_count", 0) > 0]
                    print(f"    Available: {', '.join(available)}")
                else:
                    # Just store basic info for past courses
                    student_map["courses"]["past"].append({
                        "id": course["id"],
                        "name": course["name"],
                        "term": course["term"],
                    })

            site_map["students"].append(student_map)

        return site_map

    def print_site_map(self, site_map):
        """Print site map as a tree."""
        print("\n")
        print("=" * 70)
        print("CANVAS SITE MAP - NAVIGATION TREE")
        print("=" * 70)

        for student in site_map["students"]:
            print(f"\n📁 {student['name']} (ID: {student['id']})")
            print("│")

            # Current courses
            print("├── 📂 Current Courses")
            for i, course in enumerate(student["courses"]["current"]):
                is_last = i == len(student["courses"]["current"]) - 1
                prefix = "│   └──" if is_last else "│   ├──"
                print(f"{prefix} 📚 {course['name']}")

                sections = course.get("sections", {})
                section_items = list(sections.items())
                for j, (key, section) in enumerate(section_items):
                    sec_last = j == len(section_items) - 1
                    sec_prefix = "│       └──" if sec_last else "│       ├──"
                    if is_last:
                        sec_prefix = "        └──" if sec_last else "        ├──"

                    count = section.get("item_count", 0)
                    icon = "📄"
                    if key == "assignments":
                        icon = "📝"
                    elif key == "grades":
                        icon = "📊"
                    elif key == "announcements":
                        icon = "📢"
                    elif key == "modules":
                        icon = "📦"
                    elif key == "files":
                        icon = "📁"
                    elif key == "discussions":
                        icon = "💬"

                    if count > 0:
                        print(f"{sec_prefix} {icon} {section['name']} ({count} items)")
                    else:
                        print(f"{sec_prefix} {icon} {section['name']}")

            # Past courses summary
            if student["courses"]["past"]:
                print("│")
                print(f"├── 📂 Past Courses ({len(student['courses']['past'])} courses)")
                for term in set(c["term"] for c in student["courses"]["past"]):
                    term_courses = [c for c in student["courses"]["past"] if c["term"] == term]
                    print(f"│   ├── {term}: {len(term_courses)} courses")

        print("\n")

    def close(self):
        self.driver.quit()


def main():
    print("=" * 70)
    print("CANVAS SITE MAPPER")
    print("=" * 70)

    mapper = CanvasSiteMapper(headless=True)

    try:
        if not mapper.login():
            print("Login failed")
            return

        site_map = mapper.build_full_site_map()
        mapper.print_site_map(site_map)

        # Save to file
        with open("site_map.json", "w") as f:
            json.dump(site_map, f, indent=2)
        print("Site map saved to site_map.json")

    finally:
        mapper.close()


if __name__ == "__main__":
    main()
