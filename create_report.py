"""
Create Excel report from previously collected inactive user data.
Uses only built-in libraries.
"""

import json
import csv
from datetime import date
from pathlib import Path

# Data collected from the API
CUTOFF_DATE = date(2026, 10, 5)

students_data = [
    {
        "Name": "Student Name",
        "ID Number": "12345",
        "Class Name": "Example Course",
        "Class Number": "EX 101 E01",
        "Last Login Date": "2026-10-01"
    }
]

instructors_data = [
    {
        "Name": "Instructor Name",
        "ID Number": "67890",
        "Class Name": "Example Course",
        "Class Number": "EX 101 E01",
        "Last Login Date": "2026-09-15"
    }
]

def create_csv_reports(output_dir="."):
    """Create CSV files for students and instructors."""
    output_path = Path(output_dir)

    # Students CSV
    students_file = output_path / "inactive_students.csv"
    if students_data:
        with open(students_file, 'w', newline='', encoding='utf-8') as f:
            headers = list(students_data[0].keys())
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(students_data)
        print(f"✓ Students report: {students_file}")

    # Instructors CSV
    instructors_file = output_path / "inactive_instructors.csv"
    if instructors_data:
        with open(instructors_file, 'w', newline='', encoding='utf-8') as f:
            headers = list(instructors_data[0].keys())
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(instructors_data)
        print(f"✓ Instructors report: {instructors_file}")

    # Summary
    summary_file = output_path / "report_summary.txt"
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("INACTIVE USERS REPORT\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Cutoff Date (No login since): {CUTOFF_DATE.strftime('%Y-%m-%d')}\n")
        f.write(f"Inactive Students: {len(students_data)}\n")
        f.write(f"Inactive Instructors: {len(instructors_data)}\n")
        f.write("\nColumns:\n")
        f.write("  - Name: User's full name\n")
        f.write("  - ID Number: Canvas/SIS user ID\n")
        f.write("  - Class Name: Full course name\n")
        f.write("  - Class Number: Course code (e.g., BI 111 E01)\n")
        f.write("  - Last Login Date: Last recorded activity (YYYY-MM-DD)\n")
    print(f"✓ Summary: {summary_file}")

if __name__ == "__main__":
    create_csv_reports()
    print("\nCSV files can be imported into Excel.")
