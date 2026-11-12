# Generating the Inactive Users Report

## Quick Start

You have two options to generate the Excel report of inactive students and instructors:

### Option 1: Run the improved script (Recommended)

```bash
cd "C:\Users\serit\Mississippi Valley State University\Distance Education and Online Learning - Documents\Canvas Analytics\Learning Analytics\Canvas Engagement Pulse"

python generate_inactive_report_v2.py
```

This will create:
- `inactive_users_report_students.csv` - All students not logged in since Oct 5, 2026
- `inactive_users_report_instructors.csv` - All instructors not logged in since Oct 5, 2026  
- `inactive_users_report_summary.txt` - Summary statistics
- `inactive_users_report.xlsx` - Excel workbook (if xlsxwriter is installed)

### What's Included

**Data Collected:**
- 704 inactive students
- 30 inactive instructors
- From 158 online/dual-enrollment courses
- Filtered for courses that have already started

**Report Columns:**
- **Name** - User's full name
- **ID Number** - Canvas/SIS student/employee ID
- **Class Name** - Full course name
- **Class Number** - Course code (e.g., BI 111 E01)
- **Last Login Date** - Last recorded activity (YYYY-MM-DD format, or "Never" if no login)

### Import CSV into Excel

If the Excel file doesn't create automatically, you can easily import the CSV files into Excel:

1. Open Excel
2. File → Open
3. Browse to the CSV file in your Canvas Engagement Pulse folder
4. Excel will open an import dialog where you can adjust delimiter settings
5. Click OK

### Customization

**Change the cutoff date:**
Edit `generate_inactive_report_v2.py` line ~24:
```python
CUTOFF_DATE = date(2026, 10, 5)  # Change 10, 5 to your desired month, day
```

**Include courses that haven't started yet:**
Comment out the course start check in the script or modify the `course_has_started()` function

**Change the regex pattern for online courses:**
```bash
python generate_inactive_report_v2.py --pattern "E0\d|DE"
```

## Troubleshooting

**Missing module `openpyxl` or `xlsxwriter`?**
- The script will automatically fall back to CSV format
- CSV files can be imported into Excel easily

**Permission denied running the script?**
- Make sure you're running from the correct directory
- Run: `cd "C:\Users\serit\Mississippi Valley State University\Distance Education and Online Learning - Documents\Canvas Analytics\Learning Analytics\Canvas Engagement Pulse"`
- Then run: `python generate_inactive_report_v2.py`

**Issues with Canvas connection?**
- Verify `.env` file exists with valid CANVAS_URL and CANVAS_TOKEN
- Run: `python canvas_terms.py` to test the connection

## File Locations

All output files are created in:
```
C:\Users\serit\Mississippi Valley State University\Distance Education and Online Learning - Documents\Canvas Analytics\Learning Analytics\Canvas Engagement Pulse
```
