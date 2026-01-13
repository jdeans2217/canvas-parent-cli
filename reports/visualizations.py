#!/usr/bin/env python3
"""
Visualizations - Generate charts for email reports.

Creates matplotlib charts that can be embedded in HTML emails.
"""

import os
import tempfile
from typing import List, Dict, Optional, Tuple
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for server use
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


# Color scheme matching email template
COLORS = {
    "grade_a": "#27ae60",  # Green
    "grade_b": "#2ecc71",  # Light green
    "grade_c": "#f39c12",  # Orange/yellow
    "grade_d": "#e74c3c",  # Red
    "grade_f": "#c0392b",  # Dark red
    "no_grade": "#95a5a6",  # Gray
    "background": "#f8f9fa",
    "text": "#2c3e50",
    "grid": "#ecf0f1",
}


def get_grade_color(score: Optional[float]) -> str:
    """Get color for a grade score."""
    if score is None:
        return COLORS["no_grade"]
    if score >= 90:
        return COLORS["grade_a"]
    if score >= 80:
        return COLORS["grade_b"]
    if score >= 70:
        return COLORS["grade_c"]
    if score >= 60:
        return COLORS["grade_d"]
    return COLORS["grade_f"]


def create_grades_chart(
    courses: List[Dict],
    output_path: Optional[str] = None,
    title: str = "Current Grades",
    figsize: Tuple[int, int] = (8, 4),
) -> str:
    """
    Create a horizontal bar chart of course grades.

    Args:
        courses: List of course dicts with 'name' and 'score' keys
        output_path: Path to save the chart (uses temp file if not provided)
        title: Chart title
        figsize: Figure size (width, height)

    Returns:
        Path to the saved chart image
    """
    # Filter out courses with no grades
    graded_courses = [c for c in courses if c.get("score") is not None]

    if not graded_courses:
        # Create a "no data" placeholder
        return _create_no_data_chart(output_path, "No grades available yet")

    # Sort by score (highest to lowest for display)
    graded_courses.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Prepare data
    course_names = [c.get("name", "Unknown")[:25] for c in graded_courses]  # Truncate long names
    scores = [c.get("score", 0) for c in graded_courses]
    colors = [get_grade_color(s) for s in scores]

    # Create figure
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    # Create horizontal bars
    y_pos = np.arange(len(course_names))
    bars = ax.barh(y_pos, scores, color=colors, edgecolor="white", linewidth=0.5)

    # Customize appearance
    ax.set_yticks(y_pos)
    ax.set_yticklabels(course_names, fontsize=10)
    ax.set_xlabel("Grade (%)", fontsize=11, color=COLORS["text"])
    ax.set_xlim(0, 105)  # Leave room for labels

    # Add score labels on bars
    for bar, score in zip(bars, scores):
        width = bar.get_width()
        label_x = width + 1 if width < 95 else width - 8
        ax.text(
            label_x,
            bar.get_y() + bar.get_height() / 2,
            f"{score:.0f}%",
            va="center",
            ha="left" if width < 95 else "right",
            fontsize=10,
            fontweight="bold",
            color=COLORS["text"] if width < 95 else "white",
        )

    # Add grade threshold lines
    for threshold, label in [(90, "A"), (80, "B"), (70, "C"), (60, "D")]:
        ax.axvline(x=threshold, color=COLORS["grid"], linestyle="--", linewidth=1, alpha=0.7)

    # Title
    ax.set_title(title, fontsize=14, fontweight="bold", color=COLORS["text"], pad=15)

    # Remove top and right spines
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(COLORS["grid"])
    ax.spines["bottom"].set_color(COLORS["grid"])

    # Add legend
    legend_patches = [
        mpatches.Patch(color=COLORS["grade_a"], label="A (90-100%)"),
        mpatches.Patch(color=COLORS["grade_b"], label="B (80-89%)"),
        mpatches.Patch(color=COLORS["grade_c"], label="C (70-79%)"),
        mpatches.Patch(color=COLORS["grade_d"], label="D (60-69%)"),
        mpatches.Patch(color=COLORS["grade_f"], label="F (<60%)"),
    ]
    ax.legend(
        handles=legend_patches,
        loc="lower right",
        fontsize=8,
        framealpha=0.9,
    )

    plt.tight_layout()

    # Save to file
    if output_path is None:
        output_path = tempfile.mktemp(suffix=".png")

    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    return output_path


def create_due_date_heatmap(
    assignments: List[Dict],
    output_path: Optional[str] = None,
    days: int = 7,
) -> str:
    """
    Create a 7-day calendar heatmap showing assignment density.

    Args:
        assignments: List of assignment dicts with 'due_date' key
        output_path: Path to save the chart
        days: Number of days to show

    Returns:
        Path to the saved chart image
    """
    from datetime import datetime, timedelta

    # Count assignments per day
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    day_counts = {i: 0 for i in range(days)}

    for assignment in assignments:
        due_str = assignment.get("due_at")
        if due_str:
            try:
                due_date = datetime.strptime(due_str, "%Y-%m-%dT%H:%M:%SZ")
                days_until = (due_date - today).days
                if 0 <= days_until < days:
                    day_counts[days_until] += 1
            except Exception:
                pass

    # Create figure
    fig, ax = plt.subplots(figsize=(8, 2))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    # Generate day labels and colors
    day_labels = []
    colors = []
    max_count = max(day_counts.values()) if day_counts.values() else 1

    for i in range(days):
        date = today + timedelta(days=i)
        day_labels.append(date.strftime("%a\n%d"))
        count = day_counts[i]

        # Color intensity based on count
        if count == 0:
            colors.append("#d5f5e3")  # Light green (free)
        elif count <= max_count * 0.33:
            colors.append("#f9e79f")  # Light yellow
        elif count <= max_count * 0.66:
            colors.append("#f5b041")  # Orange
        else:
            colors.append("#e74c3c")  # Red (busy)

    # Create bars
    x_pos = np.arange(days)
    counts = [day_counts[i] for i in range(days)]
    bars = ax.bar(x_pos, [1] * days, color=colors, edgecolor="white", linewidth=2)

    # Add count labels
    for i, count in enumerate(counts):
        if count > 0:
            ax.text(
                i, 0.5, str(count),
                ha="center", va="center",
                fontsize=14, fontweight="bold",
                color=COLORS["text"],
            )

    ax.set_xticks(x_pos)
    ax.set_xticklabels(day_labels, fontsize=9)
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.set_title("Upcoming Due Dates", fontsize=12, fontweight="bold", pad=10)

    # Remove spines
    for spine in ax.spines.values():
        spine.set_visible(False)

    plt.tight_layout()

    if output_path is None:
        output_path = tempfile.mktemp(suffix=".png")

    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    return output_path


def _create_no_data_chart(output_path: Optional[str], message: str) -> str:
    """Create a placeholder chart when no data is available."""
    fig, ax = plt.subplots(figsize=(6, 2))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    ax.text(
        0.5, 0.5, message,
        ha="center", va="center",
        fontsize=14, color=COLORS["no_grade"],
        style="italic",
    )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks([])
    ax.set_yticks([])

    for spine in ax.spines.values():
        spine.set_visible(False)

    if output_path is None:
        output_path = tempfile.mktemp(suffix=".png")

    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    return output_path


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    print("Visualizations Test")
    print("=" * 50)

    # Test data
    test_courses = [
        {"name": "Mathematics 3", "score": 95},
        {"name": "Science 3", "score": 88},
        {"name": "Reading/Language Arts", "score": 82},
        {"name": "Social Studies", "score": 68},
        {"name": "Art & Music", "score": 92},
    ]

    # Create test chart
    chart_path = create_grades_chart(
        test_courses,
        output_path="test_grades_chart.png",
        title="Test Grades Chart",
    )

    print(f"Chart saved to: {chart_path}")
    print("Open the file to verify the chart looks correct.")
