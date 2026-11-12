"""
Generate an Excel report of students and instructors who haven't logged
into online classes since October 5, 2026.
"""

import json
import argparse
import re
import csv
from datetime import datetime, date
from pathlib import Path
import logging

import requests

try:
    import pandas as pd
    import openpyxl
    HAS_PANDAS_OPENPYXL = True
except ImportError:
    HAS_PANDAS_OPENPYXL = False

import config

logger = logging.getLogger(__name__)

CUTOFF_DATE = date(2026, 10, 5)
DEFAULT_PATTERN = r"(E0\d|DE)"


def load_json(path: Path):
    with open(path) as f:
        return json.load(f)


def get_paginated(url: str, headers: dict) -> list:
    all_items = []
    while url:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        all_items.extend(response.json())
        url = response.links.get("next", {}).get("url")
    return all_items


def parse_date(date_str):
    """Parse Canvas ISO date string to Python date."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
    except (ValueError, AttributeError):
        return None


def select_online_courses(courses_path: Path, pattern: str) -> list:
    """Filter to online / dual-enrollment sections by course_code or name."""
    rx = re.compile(pattern, re.IGNORECASE)
    courses = load_json(courses_path)
    matched = [
        c for c in courses
        if rx.search(c.get("course_code", "") or "") or rx.search(c.get("name", "") or "")
    ]
    return matched


def course_has_started(course: dict) -> bool:
    """Check if a course has started (start_at date is in the past or None)."""
    start_at = course.get("start_at")
    if not start_at:
        return True  # Assume started if no start date
    start_date = parse_date(start_at)
    if not start_date:
        return True
    return start_date <= datetime.now().date()


def fetch_course_enrollments(course_id: int, headers: dict) -> list:
    """Fetch all enrollments for a course with their last activity dates."""
    url = f"{config.CANVAS_URL}/api/v1/courses/{course_id}/enrollments?per_page=100&include=avatar_url"
    return get_paginated(url, headers)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Excel report of inactive students/instructors in online courses."
    )
    parser.add_argument("--sis-term-id", default="202710", help="Banner term code (default: 202710)")
    parser.add_argument(
        "--pattern", default=DEFAULT_PATTERN,
        help=r"Regex for online/DE sections (default: E0\d or DE)"
    )
    parser.add_argument(
        "--output", default="inactive_users_report",
        help="Output file path (without extension - will create .xlsx, .csv, or .json)"
    )
    parser.add_argument(
        "--format", default="auto",
        choices=["auto", "xlsx", "csv", "json"],
        help="Output format (auto=try xlsx, fall back to csv)"
    )
    args = parser.parse_args()

    output_dir = Path(config.OUTPUT_DIR)
    courses_path = output_dir / f"canvas_courses_{args.sis_term_id}.json"

    if not courses_path.exists():
        logger.error("Course list not found: %s", courses_path)
        return

    matched_courses = select_online_courses(courses_path, args.pattern)
    logger.info(f"Found {len(matched_courses)} online/DE courses")

    headers = {"Authorization": f"Bearer {config.CANVAS_TOKEN}"}

    students_data = []
    instructors_data = []
    failed_courses = []

    for i, course in enumerate(matched_courses, start=1):
        course_id = course["id"]
        course_code = course.get("course_code", "N/A")
        course_name = course.get("name", "N/A")

        # Skip courses that haven't started
        if not course_has_started(course):
            logger.info(f"[{i}/{len(matched_courses)}] Skipping {course_code} - course hasn't started yet")
            continue

        logger.info(f"[{i}/{len(matched_courses)}] Fetching enrollments for {course_code}...")

        try:
            enrollments = fetch_course_enrollments(course_id, headers)

            for enrollment in enrollments:
                user = enrollment.get("user", {})
                role = enrollment.get("role", "").lower()
                last_activity = enrollment.get("last_activity_at")

                # Parse last activity date
                last_activity_date = parse_date(last_activity) if last_activity else None

                # Check if inactive (no activity or before cutoff)
                is_inactive = (
                    last_activity_date is None or
                    last_activity_date < CUTOFF_DATE
                )

                if not is_inactive:
                    continue

                row = {
                    "Name": user.get("name", "N/A"),
                    "ID Number": user.get("sis_user_id", user.get("id", "N/A")),
                    "Class Name": course_name,
                    "Class Number": course_code,
                    "Last Login Date": last_activity_date.strftime("%Y-%m-%d") if last_activity_date else "Never"
                }

                if "teacher" in role or "instructor" in role:
                    instructors_data.append(row)
                elif "student" in role:
                    students_data.append(row)

        except requests.exceptions.HTTPError as e:
            logger.warning(f"Failed to fetch enrollments for {course_code}: {e}")
            failed_courses.append({"course_id": course_id, "course_code": course_code, "error": str(e)})

    # Create Excel workbook with two sheets
    logger.info(f"Creating report with {len(students_data)} inactive students and {len(instructors_data)} inactive instructors")

    output_format = args.format
    output_base = args.output.replace('.xlsx', '').replace('.csv', '').replace('.json', '')

    # Try to create Excel file first if requested
    if output_format == "auto" or output_format == "xlsx":
        try:
            import xlsxwriter
            workbook = xlsxwriter.Workbook(f"{output_base}.xlsx")
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#D3D3D3',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })
            data_format = workbook.add_format({'border': 1})

            # Students sheet
            students_ws = workbook.add_worksheet('Students')
            if students_data:
                headers = list(students_data[0].keys())
                for col, header in enumerate(headers):
                    students_ws.write(0, col, header, header_format)
                for row, student in enumerate(students_data, start=1):
                    for col, header in enumerate(headers):
                        students_ws.write(row, col, student.get(header, ""), data_format)
                for col, header in enumerate(headers):
                    students_ws.set_column(col, col, 20)

            # Instructors sheet
            instructors_ws = workbook.add_worksheet('Instructors')
            if instructors_data:
                headers = list(instructors_data[0].keys())
                for col, header in enumerate(headers):
                    instructors_ws.write(0, col, header, header_format)
                for row, instructor in enumerate(instructors_data, start=1):
                    for col, header in enumerate(headers):
                        instructors_ws.write(row, col, instructor.get(header, ""), data_format)
                for col, header in enumerate(headers):
                    instructors_ws.set_column(col, col, 20)

            # Summary sheet
            summary_ws = workbook.add_worksheet('Summary')
            summary_data = [
                ["Cutoff Date (Since)", CUTOFF_DATE.strftime("%Y-%m-%d")],
                ["Online/DE Courses Checked", len(matched_courses) - len(failed_courses)],
                ["Inactive Students", len(students_data)],
                ["Inactive Instructors", len(instructors_data)],
                ["Failed Courses", len(failed_courses)],
                ["Report Generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
            ]
            for row, (metric, value) in enumerate(summary_data):
                summary_ws.write(row, 0, metric, header_format)
                summary_ws.write(row, 1, value, data_format)
            summary_ws.set_column(0, 0, 30)
            summary_ws.set_column(1, 1, 30)

            workbook.close()
            logger.info(f"Excel report saved to {output_base}.xlsx")
            return

        except (ImportError, Exception) as e:
            logger.warning(f"Could not create Excel file: {e}")
            if output_format == "xlsx":
                logger.error("Format set to xlsx but xlsxwriter not available")
                return
            output_format = "csv"

    # Create CSV files
    if output_format == "auto" or output_format == "csv":
        # Students CSV
        if students_data:
            students_csv = f"{output_base}_students.csv"
            with open(students_csv, 'w', newline='', encoding='utf-8') as f:
                headers = list(students_data[0].keys())
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(students_data)
            logger.info(f"Students report saved to {students_csv}")

        # Instructors CSV
        if instructors_data:
            instructors_csv = f"{output_base}_instructors.csv"
            with open(instructors_csv, 'w', newline='', encoding='utf-8') as f:
                headers = list(instructors_data[0].keys())
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(instructors_data)
            logger.info(f"Instructors report saved to {instructors_csv}")

        # Summary
        summary_file = f"{output_base}_summary.txt"
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("INACTIVE USERS REPORT - SUMMARY\n")
            f.write("=" * 70 + "\n\n")
            f.write(f"Cutoff Date (No login since): {CUTOFF_DATE.strftime('%Y-%m-%d')}\n")
            f.write(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"Online/DE Courses Checked: {len(matched_courses) - len(failed_courses)}\n")
            f.write(f"Inactive Students: {len(students_data)}\n")
            f.write(f"Inactive Instructors: {len(instructors_data)}\n")
            f.write(f"Failed Courses: {len(failed_courses)}\n\n")
            f.write("Column Definitions:\n")
            f.write("  - Name: User's full name\n")
            f.write("  - ID Number: Canvas/SIS user ID\n")
            f.write("  - Class Name: Full course name\n")
            f.write("  - Class Number: Course code (e.g., BI 111 E01)\n")
            f.write("  - Last Login Date: Last recorded activity (YYYY-MM-DD or 'Never')\n")
        logger.info(f"Summary saved to {summary_file}")

    # Create JSON for potential future use
    if output_format == "json":
        json_file = f"{output_base}.json"
        data = {
            "metadata": {
                "report_generated": datetime.now().isoformat(),
                "cutoff_date": CUTOFF_DATE.isoformat(),
                "courses_checked": len(matched_courses) - len(failed_courses),
                "failed_courses": len(failed_courses)
            },
            "students": students_data,
            "instructors": instructors_data
        }
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        logger.info(f"JSON report saved to {json_file}")


if __name__ == "__main__":
    main()
