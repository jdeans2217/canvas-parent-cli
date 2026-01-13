"""
Reports module for Canvas Parent CLI.

Provides data collection, visualization, and report building.
"""

from reports.data_collector import DataCollector
from reports.visualizations import create_grades_chart
from reports.report_builder import ReportBuilder

__all__ = [
    "DataCollector",
    "create_grades_chart",
    "ReportBuilder",
]
