#!/usr/bin/env python3
"""
Find where teachers put their schedule/agenda information in Canvas.

Audits all courses to find pages, modules, and other resources that contain
schedule-like content.
"""

import sys
import re
sys.path.insert(0, '/home/jasondeans/learn/canvas_api/simple_tests')

import canvas_api
from bs4 import BeautifulSoup


def extract_text(html):
    """Extract plain text from HTML."""
    if not html:
        return ""
    soup = BeautifulSoup(html, 'lxml')
    return soup.get_text(separator=' ', strip=True)[:500]


def has_schedule_content(text):
    """Check if text contains schedule-like keywords."""
    keywords = [
        'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
        'homework', 'classwork', 'assignment', 'due', 'quiz', 'test',
        'lesson', 'chapter', 'reading', 'practice', 'review',
        'in class', 'at home', 'objectives', 'agenda', 'schedule',
        'this week', 'today', 'tomorrow'
    ]
    text_lower = text.lower()
    matches = [kw for kw in keywords if kw in text_lower]
    return matches


def audit_course(course_id, course_name):
    """Audit a single course for schedule information locations."""
    print(f"\n{'='*70}")
    print(f"COURSE: {course_name}")
    print(f"ID: {course_id}")
    print('='*70)

    findings = {
        'course_id': course_id,
        'course_name': course_name,
        'schedule_locations': []
    }

    # 1. Check all Pages
    print("\n--- PAGES ---")
    pages = canvas_api.get_course_pages(course_id)
    print(f"Total pages: {len(pages)}")

    schedule_pages = []
    for page in pages:
        title = page.get('title', '')
        url = page.get('url', '')

        # Get page content
        content = canvas_api.get_page_content(course_id, url)
        if content:
            body = content.get('body', '')
            text = extract_text(body)
            matches = has_schedule_content(text)

            if matches:
                schedule_pages.append({
                    'title': title,
                    'url': url,
                    'keywords': matches[:5],
                    'preview': text[:150]
                })

    if schedule_pages:
        print(f"\nPages with schedule content ({len(schedule_pages)}):")
        for p in schedule_pages[:10]:
            print(f"  - {p['title']}")
            print(f"    Keywords: {', '.join(p['keywords'][:5])}")
            print(f"    Preview: {p['preview'][:80]}...")
        findings['schedule_locations'].append({
            'type': 'pages',
            'count': len(schedule_pages),
            'items': schedule_pages[:10]
        })
    else:
        print("  No schedule content found in pages")

    # 2. Check Modules
    print("\n--- MODULES ---")
    modules = canvas_api.get_course_modules(course_id)
    print(f"Total modules: {len(modules)}")

    for mod in modules[:5]:
        mod_name = mod.get('name', '')
        items = mod.get('items', [])
        print(f"\n  Module: {mod_name} ({len(items)} items)")

        for item in items[:5]:
            item_type = item.get('type', '')
            item_title = item.get('title', '')
            print(f"    - [{item_type}] {item_title[:50]}")

    if modules:
        findings['schedule_locations'].append({
            'type': 'modules',
            'count': len(modules),
            'names': [m.get('name', '') for m in modules[:10]]
        })

    # 3. Check Syllabus
    print("\n--- SYLLABUS ---")
    course_detail = canvas_api.api_get(f"/courses/{course_id}", {"include[]": "syllabus_body"})
    if course_detail:
        syllabus = course_detail.get('syllabus_body', '')
        if syllabus:
            text = extract_text(syllabus)
            matches = has_schedule_content(text)
            print(f"  Has syllabus content: Yes ({len(text)} chars)")
            if matches:
                print(f"  Keywords found: {', '.join(matches[:5])}")
                print(f"  Preview: {text[:150]}...")
                findings['schedule_locations'].append({
                    'type': 'syllabus',
                    'keywords': matches[:5],
                    'preview': text[:200]
                })
        else:
            print("  Has syllabus content: No")

    # 4. Check Front Page
    print("\n--- FRONT PAGE ---")
    front_page = canvas_api.api_get(f"/courses/{course_id}/front_page")
    if front_page:
        title = front_page.get('title', '')
        body = front_page.get('body', '')
        text = extract_text(body)
        matches = has_schedule_content(text)
        print(f"  Front page: {title}")
        if matches:
            print(f"  Keywords: {', '.join(matches[:5])}")
            print(f"  Preview: {text[:150]}...")
            findings['schedule_locations'].append({
                'type': 'front_page',
                'title': title,
                'keywords': matches[:5]
            })
    else:
        print("  No front page set")

    # 5. Check Announcements
    print("\n--- RECENT ANNOUNCEMENTS ---")
    announcements = canvas_api.get_course_announcements(course_id)
    print(f"Total announcements: {len(announcements)}")
    for ann in announcements[:3]:
        title = ann.get('title', '')
        message = extract_text(ann.get('message', ''))[:100]
        print(f"  - {title}")
        if message:
            print(f"    {message}...")

    return findings


def main():
    print("CANVAS SCHEDULE FINDER")
    print("=" * 70)
    print("Finding where teachers put schedule/agenda information...")

    students = canvas_api.get_students()
    print(f"\nFound {len(students)} students")

    all_findings = {}

    for student in students:
        student_name = student.get('name', 'Unknown')
        student_id = student.get('id')

        print(f"\n{'#'*70}")
        print(f"STUDENT: {student_name}")
        print('#'*70)

        courses = canvas_api.get_student_courses(student_id)
        print(f"Found {len(courses)} active courses")

        for course in courses:
            course_id = course['id']
            course_name = course.get('name', 'Unknown')

            # Skip already audited (shared courses)
            if course_id in all_findings:
                print(f"\n[Skipping {course_name} - already audited]")
                continue

            # Skip school-wide courses
            if 'thales academy' in course_name.lower() and 'k-8' in course_name.lower():
                print(f"\n[Skipping {course_name} - school-wide]")
                continue

            findings = audit_course(course_id, course_name)
            all_findings[course_id] = findings

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY: Where teachers put schedule info")
    print("=" * 70)

    for course_id, findings in all_findings.items():
        course_name = findings['course_name']
        locations = findings['schedule_locations']

        print(f"\n{course_name}:")
        if locations:
            for loc in locations:
                loc_type = loc['type']
                if loc_type == 'pages':
                    print(f"  - Pages: {loc['count']} pages with schedule content")
                    for item in loc.get('items', [])[:3]:
                        print(f"      * {item['title']}")
                elif loc_type == 'modules':
                    print(f"  - Modules: {', '.join(loc['names'][:3])}")
                elif loc_type == 'syllabus':
                    print(f"  - Syllabus: Has schedule content")
                elif loc_type == 'front_page':
                    print(f"  - Front Page: {loc['title']}")
        else:
            print("  - No schedule content found")


if __name__ == "__main__":
    main()
