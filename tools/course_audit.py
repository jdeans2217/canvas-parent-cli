#!/usr/bin/env python3
"""
Canvas Course Audit - Analyze how different teachers use Canvas features
"""

import sys
sys.path.insert(0, '/home/jasondeans/learn/canvas_api/simple_tests')

from canvas_api import api_get, api_get_all, get_students, get_student_courses
import json

def audit_course(course_id, course_name):
    """Audit a single course for all available features."""
    print(f"\n{'='*60}")
    print(f"COURSE: {course_name}")
    print(f"ID: {course_id}")
    print('='*60)

    audit = {
        'course_id': course_id,
        'course_name': course_name,
        'features': {}
    }

    # 1. Course Details
    course = api_get(f"/courses/{course_id}")
    if course:
        audit['syllabus'] = bool(course.get('syllabus_body'))
        audit['public_syllabus'] = course.get('public_syllabus', False)
        audit['default_view'] = course.get('default_view', 'unknown')
        print(f"\nDefault View: {audit['default_view']}")
        print(f"Has Syllabus: {audit['syllabus']}")

    # 2. Tabs (what's enabled)
    tabs = api_get(f"/courses/{course_id}/tabs")
    if tabs:
        visible_tabs = [t['label'] for t in tabs if t.get('visibility') == 'public' or not t.get('hidden', True)]
        audit['features']['tabs'] = visible_tabs
        print(f"\nEnabled Tabs ({len(visible_tabs)}): {', '.join(visible_tabs)}")

    # 3. Modules
    modules = api_get_all(f"/courses/{course_id}/modules")
    audit['features']['modules'] = {
        'count': len(modules) if modules else 0,
        'names': [m.get('name', '') for m in (modules or [])[:5]]
    }
    print(f"\nModules: {audit['features']['modules']['count']}")
    if modules:
        for m in modules[:5]:
            items_count = m.get('items_count', 0)
            print(f"  - {m.get('name')} ({items_count} items)")

    # 4. Assignment Groups (grading categories)
    groups = api_get_all(f"/courses/{course_id}/assignment_groups")
    audit['features']['assignment_groups'] = []
    if groups:
        print(f"\nAssignment Groups ({len(groups)}):")
        for g in groups:
            group_info = {
                'name': g.get('name', ''),
                'weight': g.get('group_weight', 0),
                'position': g.get('position', 0)
            }
            audit['features']['assignment_groups'].append(group_info)
            weight = g.get('group_weight', 0)
            if weight:
                print(f"  - {g.get('name')}: {weight}%")
            else:
                print(f"  - {g.get('name')}")

    # 5. Assignments
    assignments = api_get_all(f"/courses/{course_id}/assignments")
    audit['features']['assignments'] = {
        'count': len(assignments) if assignments else 0,
        'types': {}
    }
    if assignments:
        for a in assignments:
            sub_types = a.get('submission_types', [])
            for st in sub_types:
                audit['features']['assignments']['types'][st] = audit['features']['assignments']['types'].get(st, 0) + 1
        print(f"\nAssignments: {len(assignments)}")
        print(f"  Submission Types: {audit['features']['assignments']['types']}")

    # 6. Discussion Topics
    discussions = api_get_all(f"/courses/{course_id}/discussion_topics")
    audit['features']['discussions'] = {
        'count': len(discussions) if discussions else 0,
        'recent': [d.get('title', '') for d in (discussions or [])[:3]]
    }
    print(f"\nDiscussions: {audit['features']['discussions']['count']}")
    if discussions:
        for d in discussions[:3]:
            print(f"  - {d.get('title', 'Untitled')}")

    # 7. Announcements
    announcements = api_get("/announcements", {"context_codes[]": f"course_{course_id}"})
    audit['features']['announcements'] = {
        'count': len(announcements) if announcements else 0,
        'recent': [a.get('title', '') for a in (announcements or [])[:3]]
    }
    print(f"\nAnnouncements: {audit['features']['announcements']['count']}")
    if announcements:
        for a in announcements[:3]:
            print(f"  - {a.get('title', 'Untitled')}")

    # 8. Pages
    pages = api_get_all(f"/courses/{course_id}/pages")
    audit['features']['pages'] = {
        'count': len(pages) if pages else 0,
        'titles': [p.get('title', '') for p in (pages or [])[:5]]
    }
    print(f"\nPages: {audit['features']['pages']['count']}")
    if pages:
        for p in pages[:5]:
            print(f"  - {p.get('title', 'Untitled')}")

    # 9. Quizzes
    quizzes = api_get_all(f"/courses/{course_id}/quizzes")
    audit['features']['quizzes'] = {
        'count': len(quizzes) if quizzes else 0
    }
    print(f"\nQuizzes: {audit['features']['quizzes']['count']}")

    # 10. Files
    files = api_get_all(f"/courses/{course_id}/files")
    audit['features']['files'] = {
        'count': len(files) if files else 0
    }
    print(f"\nFiles: {audit['features']['files']['count']}")

    # 11. Rubrics
    rubrics = api_get_all(f"/courses/{course_id}/rubrics")
    audit['features']['rubrics'] = {
        'count': len(rubrics) if rubrics else 0
    }
    print(f"\nRubrics: {audit['features']['rubrics']['count']}")

    # 12. External Tools
    tools = api_get_all(f"/courses/{course_id}/external_tools")
    audit['features']['external_tools'] = {
        'count': len(tools) if tools else 0,
        'names': [t.get('name', '') for t in (tools or [])[:5]]
    }
    print(f"\nExternal Tools: {audit['features']['external_tools']['count']}")
    if tools:
        for t in tools[:5]:
            print(f"  - {t.get('name', 'Unknown')}")

    # 13. Grading Standard
    if course:
        grading = course.get('grading_standard_id')
        audit['grading_standard'] = grading
        print(f"\nGrading Standard ID: {grading or 'Default/None'}")

    return audit


def main():
    """Run the full course audit."""
    print("CANVAS COURSE AUDIT - Teacher Usage Analysis")
    print("=" * 60)

    # Get students
    students = get_students()
    print(f"\nFound {len(students)} students")

    all_audits = {}

    for student in students:
        student_name = student.get('name', 'Unknown')
        student_id = student.get('id')
        print(f"\n{'#'*60}")
        print(f"STUDENT: {student_name} (ID: {student_id})")
        print('#'*60)

        courses = get_student_courses(student_id)
        print(f"Found {len(courses)} active courses")

        for course in courses:
            course_id = course['id']
            course_name = course.get('name', 'Unknown')

            # Skip if already audited (shared courses)
            if course_id in all_audits:
                print(f"\n[Skipping {course_name} - already audited]")
                continue

            audit = audit_course(course_id, course_name)
            all_audits[course_id] = audit

    # Summary comparison
    print("\n" + "=" * 60)
    print("SUMMARY COMPARISON")
    print("=" * 60)

    print("\n{:<40} {:>8} {:>8} {:>8} {:>8} {:>8}".format(
        "Course", "Modules", "Discuss", "Announce", "Pages", "Rubrics"
    ))
    print("-" * 80)

    for course_id, audit in all_audits.items():
        name = audit['course_name'][:38]
        f = audit['features']
        print("{:<40} {:>8} {:>8} {:>8} {:>8} {:>8}".format(
            name,
            f.get('modules', {}).get('count', 0),
            f.get('discussions', {}).get('count', 0),
            f.get('announcements', {}).get('count', 0),
            f.get('pages', {}).get('count', 0),
            f.get('rubrics', {}).get('count', 0)
        ))

    # Save to JSON
    with open('/home/jasondeans/learn/canvas_api/simple_tests/tools/course_audit_results.json', 'w') as f:
        json.dump(all_audits, f, indent=2)
    print("\nFull audit saved to tools/course_audit_results.json")

    return all_audits


if __name__ == "__main__":
    main()
