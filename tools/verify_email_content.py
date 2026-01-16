#!/usr/bin/env python3
"""
Verify Email Content Against Canvas Website

Compares the daily debrief email content with actual data on Canvas website.
"""

import os
import sys
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

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import canvas_api
from reports.debrief_collector import DebriefCollector

load_dotenv()

BASE_URL = os.getenv("CANVAS_API_URL", "https://thalesacademy.instructure.com")
USERNAME = os.getenv("CANVAS_USERNAME")
PASSWORD = os.getenv("CANVAS_PASSWORD")


class ContentVerifier:
    def __init__(self, headless=True):
        self.base_url = BASE_URL
        self.driver = None
        self.headless = headless

    def setup_driver(self):
        """Initialize Chrome driver."""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10)

    def login(self):
        """Login to Canvas."""
        print("Logging in to Canvas...")
        self.driver.get(f"{self.base_url}/login/canvas")
        time.sleep(2)

        try:
            username_field = self.wait.until(
                EC.element_to_be_clickable((By.ID, "pseudonym_session_unique_id"))
            )
            username_field.clear()
            username_field.send_keys(USERNAME)

            password_field = self.driver.find_element(By.ID, "pseudonym_session_password")
            password_field.clear()
            password_field.send_keys(PASSWORD)

            submit_button = self.driver.find_element(By.CSS_SELECTOR, "input[type='submit']")
            submit_button.click()

            time.sleep(3)

            # Check for successful login - dashboard content or login_success param
            if "login_success" in self.driver.current_url or "Dashboard" in self.driver.page_source:
                print("Login successful!")
                return True
            if "login" not in self.driver.current_url:
                print("Login successful!")
                return True
            return False

        except Exception as e:
            print(f"Login error: {e}")
            return False

    def get_website_grades(self, course_id):
        """Get grades from website for a course."""
        url = f"{self.base_url}/courses/{course_id}/grades"
        self.driver.get(url)
        time.sleep(2)

        grades = []
        try:
            # Look for grade table
            grade_rows = self.driver.find_elements(By.CSS_SELECTOR, "#grades_summary tr.student_assignment")
            for row in grade_rows[:20]:
                try:
                    name_elem = row.find_element(By.CSS_SELECTOR, "th.title a, th.title")
                    score_elem = row.find_element(By.CSS_SELECTOR, ".grade")

                    name = name_elem.text.strip()
                    score = score_elem.text.strip()

                    if name and score:
                        grades.append({"name": name, "score": score})
                except:
                    pass
        except Exception as e:
            print(f"  Error getting grades: {e}")

        return grades

    def get_website_upcoming(self, course_id):
        """Get upcoming assignments from website."""
        url = f"{self.base_url}/courses/{course_id}/assignments"
        self.driver.get(url)
        time.sleep(2)

        assignments = []
        try:
            # Look for assignment rows
            rows = self.driver.find_elements(By.CSS_SELECTOR, ".ig-row, .assignment")
            for row in rows[:20]:
                try:
                    name = row.find_element(By.CSS_SELECTOR, ".ig-title, .title a").text.strip()
                    due = ""
                    try:
                        due = row.find_element(By.CSS_SELECTOR, ".assignment-date-due, .due_date").text.strip()
                    except:
                        pass
                    if name:
                        assignments.append({"name": name, "due": due})
                except:
                    pass
        except Exception as e:
            print(f"  Error getting assignments: {e}")

        return assignments

    def get_website_modules(self, course_id):
        """Get modules/agenda from website."""
        url = f"{self.base_url}/courses/{course_id}/modules"
        self.driver.get(url)
        time.sleep(2)

        modules = []
        try:
            module_items = self.driver.find_elements(By.CSS_SELECTOR, ".context_module")
            for module in module_items[:10]:
                try:
                    title = module.find_element(By.CSS_SELECTOR, ".name, .ig-header-title").text.strip()
                    items = []
                    for item in module.find_elements(By.CSS_SELECTOR, ".ig-row .ig-title, .context_module_item .title")[:5]:
                        items.append(item.text.strip())
                    modules.append({"title": title, "items": items})
                except:
                    pass
        except Exception as e:
            print(f"  Error getting modules: {e}")

        return modules

    def close(self):
        """Close the browser."""
        if self.driver:
            self.driver.quit()


def run_verification():
    """Run the content verification."""
    print("=" * 70)
    print("EMAIL vs WEBSITE CONTENT VERIFICATION")
    print("=" * 70)
    print()

    # Step 1: Get email data
    print("Step 1: Collecting email data from API...")
    print("-" * 50)

    students = canvas_api.get_students()
    email_data = {}

    for student in students:
        student_id = student["id"]
        student_name = student["name"]
        print(f"\n  {student_name} (ID: {student_id})")

        collector = DebriefCollector(student_id, student_name)
        debrief = collector.collect()

        email_data[student_id] = {
            "name": student_name,
            "grades": debrief.grades_posted_today,
            "missing": debrief.missing_assignments,
            "upcoming": [],  # We'll populate this
            "agendas": debrief.today_agendas,
        }

        # Get upcoming from API
        upcoming = canvas_api.get_upcoming_assignments(student_id, days=5)
        email_data[student_id]["upcoming"] = upcoming or []

        print(f"    - {len(debrief.grades_posted_today)} grades posted today")
        print(f"    - {len(debrief.missing_assignments)} missing assignments")
        print(f"    - {len(upcoming or [])} upcoming assignments")
        print(f"    - {len(debrief.today_agendas)} courses with agendas")

    print()
    print("=" * 70)
    print("Step 2: Fetching website data via Selenium...")
    print("-" * 50)

    verifier = ContentVerifier(headless=True)
    verifier.setup_driver()

    website_data = {}

    try:
        if not verifier.login():
            print("Failed to login!")
            return

        for student_id, data in email_data.items():
            student_name = data["name"]
            print(f"\n  Checking {student_name}...")

            website_data[student_id] = {
                "name": student_name,
                "courses": {}
            }

            # Get courses for this student
            courses = canvas_api.get_student_courses(student_id)

            for course in courses[:10]:  # Limit to 10 courses
                course_id = course["id"]
                course_name = course["name"]
                short_name = course_name.split(" - ")[0][:30]

                print(f"    Course: {short_name}")

                # Get website data for this course
                web_grades = verifier.get_website_grades(course_id)
                web_assignments = verifier.get_website_upcoming(course_id)
                web_modules = verifier.get_website_modules(course_id)

                website_data[student_id]["courses"][course_id] = {
                    "name": course_name,
                    "grades": web_grades,
                    "assignments": web_assignments,
                    "modules": web_modules,
                }

                print(f"      - {len(web_grades)} grades found")
                print(f"      - {len(web_assignments)} assignments found")
                print(f"      - {len(web_modules)} modules found")

    finally:
        verifier.close()

    print()
    print("=" * 70)
    print("Step 3: Comparison Report")
    print("=" * 70)

    for student_id, data in email_data.items():
        student_name = data["name"]
        print(f"\n{'='*50}")
        print(f"STUDENT: {student_name}")
        print(f"{'='*50}")

        web_student = website_data.get(student_id, {})

        # Compare grades posted today
        print(f"\n  GRADES POSTED TODAY (Email shows {len(data['grades'])} grades)")
        if data['grades']:
            for g in data['grades']:
                print(f"    - {g.get('name', 'N/A')}: {g.get('score', 'N/A')}/{g.get('points_possible', 'N/A')}")
        else:
            print("    (none)")

        # Compare missing assignments
        print(f"\n  MISSING ASSIGNMENTS (Email shows {len(data['missing'])} missing)")
        if data['missing']:
            for m in data['missing']:
                print(f"    - {m.get('name', 'N/A')} (due: {m.get('due_date', 'N/A')})")
        else:
            print("    (none)")

        # Compare upcoming
        print(f"\n  UPCOMING (Email shows {len(data['upcoming'])} upcoming)")
        for u in data['upcoming'][:5]:
            print(f"    - {u.get('name', 'N/A')}")

        # Compare agendas
        print(f"\n  TODAY'S AGENDAS (Email shows {len(data['agendas'])} courses)")
        for course_name, agenda in data['agendas'].items():
            short_name = course_name.split(" - ")[0][:25]
            if agenda.in_class:
                print(f"    - {short_name}: {agenda.in_class[0][:50]}...")
            elif agenda.learning_objectives:
                print(f"    - {short_name}: {agenda.learning_objectives[0][:50]}...")

        # Website data for comparison
        print(f"\n  WEBSITE DATA:")
        web_courses = web_student.get("courses", {})
        for course_id, course_data in list(web_courses.items())[:5]:
            short_name = course_data["name"].split(" - ")[0][:25]
            print(f"    Course: {short_name}")
            print(f"      Grades on site: {len(course_data['grades'])}")
            print(f"      Assignments on site: {len(course_data['assignments'])}")
            if course_data['modules']:
                print(f"      Modules: {course_data['modules'][0]['title'][:40] if course_data['modules'] else 'none'}")

    print()
    print("=" * 70)
    print("VERIFICATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    run_verification()
