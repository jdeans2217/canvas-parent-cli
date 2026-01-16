#!/usr/bin/env python3
"""
Agenda Parser - Parse weekly agenda pages from Canvas.

Extracts day-specific content (In Class, At Home/Homework, Learning Objectives)
from HTML weekly agenda pages.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag


@dataclass
class DayAgenda:
    """Parsed content for a single day."""
    day_name: str
    learning_objectives: List[str] = field(default_factory=list)
    in_class: List[str] = field(default_factory=list)
    at_home: List[str] = field(default_factory=list)

    def has_content(self) -> bool:
        """Check if this day has any content."""
        return bool(self.learning_objectives or self.in_class or self.at_home)


@dataclass
class WeeklyAgenda:
    """Parsed weekly agenda with date range."""
    week_title: str  # e.g., "Quarter 1, Week 1"
    date_range: str  # e.g., "July 21-25, 2025"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    days: Dict[str, DayAgenda] = field(default_factory=dict)

    def get_day(self, day_name: str) -> Optional[DayAgenda]:
        """Get agenda for a specific day (case-insensitive)."""
        return self.days.get(day_name.capitalize())

    def contains_date(self, target_date: date) -> bool:
        """Check if this week contains the given date."""
        if self.start_date and self.end_date:
            return self.start_date <= target_date <= self.end_date
        return False


class AgendaParser:
    """Parser for weekly agenda HTML content from Canvas."""

    DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    def parse(self, html_content: str) -> WeeklyAgenda:
        """
        Parse weekly agenda HTML into structured data.

        Args:
            html_content: Raw HTML from Canvas page body

        Returns:
            WeeklyAgenda with parsed content
        """
        soup = BeautifulSoup(html_content, "lxml")

        # Extract week title and date range from subtitle
        week_title, date_range = self._extract_header_info(soup)
        start_date, end_date = self._parse_date_range(date_range)

        agenda = WeeklyAgenda(
            week_title=week_title,
            date_range=date_range,
            start_date=start_date,
            end_date=end_date,
        )

        # Find and parse each day's content
        for day_name in self.DAYS_OF_WEEK:
            day_agenda = self._parse_day(soup, day_name)
            if day_agenda:
                agenda.days[day_name] = day_agenda

        return agenda

    def get_day_agenda(self, html_content: str, target_day: str) -> Optional[DayAgenda]:
        """
        Extract agenda for a specific day.

        Args:
            html_content: Raw HTML from Canvas page body
            target_day: Day name (e.g., "Monday")

        Returns:
            DayAgenda for the specified day, or None
        """
        agenda = self.parse(html_content)
        return agenda.get_day(target_day)

    def _extract_header_info(self, soup: BeautifulSoup) -> Tuple[str, str]:
        """Extract week title and date range from page header."""
        week_title = ""
        date_range = ""

        # Look for subtitle with date range (e.g., "Quarter 1, Week 1 | July 21-25, 2025")
        subtitle = soup.find("p", class_="kl_subtitle")
        if subtitle:
            text = subtitle.get_text(strip=True)
            if "|" in text:
                parts = text.split("|", 1)
                week_title = parts[0].strip()
                date_range = parts[1].strip() if len(parts) > 1 else ""
            else:
                week_title = text

        return week_title, date_range

    def _parse_date_range(self, date_range: str) -> Tuple[Optional[date], Optional[date]]:
        """
        Parse date range string into start and end dates.

        Handles formats like:
        - "July 21-25, 2025"
        - "January 6-10, 2026"
        - "Dec 9-13, 2025"
        """
        if not date_range:
            return None, None

        # Pattern: "Month Day-Day, Year"
        pattern = r"(\w+)\s+(\d+)-(\d+),?\s*(\d{4})"
        match = re.search(pattern, date_range)

        if match:
            month_str, start_day, end_day, year = match.groups()
            try:
                # Parse month name
                month_date = datetime.strptime(month_str[:3], "%b")
                month = month_date.month
                year_int = int(year)

                start = date(year_int, month, int(start_day))
                end = date(year_int, month, int(end_day))
                return start, end
            except (ValueError, AttributeError):
                pass

        return None, None

    def _parse_day(self, soup: BeautifulSoup, day_name: str) -> Optional[DayAgenda]:
        """
        Parse content for a specific day from the HTML.

        Looks for <h3> with the day name and extracts content until next <h3>.
        """
        day_agenda = DayAgenda(day_name=day_name)

        # Find h3 containing the day name
        day_header = None
        for h3 in soup.find_all("h3"):
            if day_name.lower() in h3.get_text().lower():
                day_header = h3
                break

        if not day_header:
            return None

        # Get all content between this h3 and the next h3
        current = day_header.find_next_sibling()
        day_content = []

        while current:
            if current.name == "h3":
                # Check if this is another day header
                text = current.get_text().lower()
                if any(day.lower() in text for day in self.DAYS_OF_WEEK):
                    break
            day_content.append(current)
            current = current.find_next_sibling()

        # Parse the collected content for subsections
        self._parse_subsections(day_content, day_agenda)

        return day_agenda if day_agenda.has_content() else None

    def _parse_subsections(self, elements: List[Tag], day_agenda: DayAgenda):
        """Parse h4 subsections within a day's content."""
        current_section = None

        for element in elements:
            if not hasattr(element, "name"):
                continue

            # Check for section headers (h4)
            if element.name == "h4":
                section_text = element.get_text().lower()
                if "learning" in section_text or "objective" in section_text or "essential" in section_text:
                    current_section = "learning_objectives"
                elif "in class" in section_text or "classwork" in section_text:
                    current_section = "in_class"
                elif "at home" in section_text or "homework" in section_text or "home" in section_text:
                    current_section = "at_home"
                else:
                    current_section = None

            # Extract list items for current section
            elif element.name in ("ul", "ol") and current_section:
                items = self._extract_list_items(element)
                if current_section == "learning_objectives":
                    day_agenda.learning_objectives.extend(items)
                elif current_section == "in_class":
                    day_agenda.in_class.extend(items)
                elif current_section == "at_home":
                    day_agenda.at_home.extend(items)

            # Also check for nested lists within divs
            elif element.name == "div" and current_section:
                for ul in element.find_all(["ul", "ol"]):
                    items = self._extract_list_items(ul)
                    if current_section == "learning_objectives":
                        day_agenda.learning_objectives.extend(items)
                    elif current_section == "in_class":
                        day_agenda.in_class.extend(items)
                    elif current_section == "at_home":
                        day_agenda.at_home.extend(items)

    def _extract_list_items(self, list_element: Tag) -> List[str]:
        """Extract text from list items, cleaning up whitespace."""
        items = []
        for li in list_element.find_all("li", recursive=False):
            # Get text, preserving some structure but removing excessive whitespace
            text = li.get_text(separator=" ", strip=True)
            # Clean up multiple spaces
            text = re.sub(r"\s+", " ", text)
            if text and text.lower() not in ("none", "n/a", "-"):
                items.append(text)
        return items


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/home/jasondeans/learn/canvas_api/simple_tests")

    import canvas_api

    print("Agenda Parser Test")
    print("=" * 50)

    # Fetch a sample page
    course_id = 22555  # Math - Saxon 3
    page_url = "q1w1"

    print(f"Fetching page: courses/{course_id}/pages/{page_url}")
    page = canvas_api.get_page_content(course_id, page_url)

    if not page:
        print("Failed to fetch page")
        exit(1)

    html = page.get("body", "")
    print(f"Page body length: {len(html)} chars")

    parser = AgendaParser()
    agenda = parser.parse(html)

    print(f"\nWeek Title: {agenda.week_title}")
    print(f"Date Range: {agenda.date_range}")
    print(f"Start Date: {agenda.start_date}")
    print(f"End Date: {agenda.end_date}")

    print(f"\nDays parsed: {list(agenda.days.keys())}")

    for day_name, day in agenda.days.items():
        print(f"\n{day_name}:")
        if day.learning_objectives:
            print(f"  Learning Objectives: {day.learning_objectives[:2]}")
        if day.in_class:
            print(f"  In Class: {day.in_class[:2]}")
        if day.at_home:
            print(f"  At Home: {day.at_home[:2]}")
