r"""
build_pbi_model.py — Write the Power BI source workbook (canvas_pbi_model.xlsx)
from an analytics_bundle.json written by canvas_analytics_pull.py.

canvas_analytics_pull.py calls this automatically at the end of every full
run. It can also be run on its own to rebuild from an existing bundle.

Usage:
    python build_pbi_model.py output/analytics/202710/analytics_bundle.json

Output:
    output/canvas_pbi_model_<YYYY-MM-DD>.xlsx          (dated copy, kept)
    <DASHBOARD_EXPORT_DIR>/canvas_pbi_model.xlsx       (overwritten each run)

Analytics.pbix imports from canvas_pbi_model.xlsx. The workbook is only the
data source: open Analytics.pbix in Power BI Desktop and click Refresh to
pull the new data into the report.

Sheets (one per Power BI table; names and columns must stay stable or the
.pbix queries break):
    Dim_Course, Dim_Student, Dim_FailedCourse,
    Fact_Enrollment, Fact_CourseDailyActivity, Fact_AccountDailyActivity,
    Fact_ContentTypeViews, Fact_AccountStatistics,
    Fact_GradeDist_Summer2026, Fact_CourseGrades_Summer2026 (from output/dashboard_grades.json)
"""

import argparse
import logging
import shutil
from pathlib import Path

import pandas as pd

import config
from build_dashboard import EXPORT_DIR, EMPTY_GRADES, load_json, n, student_names, term_name

logger = logging.getLogger(__name__)

EXPORT_NAME = "canvas_pbi_model.xlsx"


def build_tables(bundle: dict) -> dict[str, pd.DataFrame]:
    names = student_names(bundle)
    summaries = bundle["course_student_summaries"]

    enrollments = []
    for c in summaries:
        for s in c["student_summaries"]:
            tb = s.get("tardiness_breakdown") or {}
            enrollments.append({
                "UserId": s["id"],
                "UserName": names.get(s["id"]),
                "CourseId": c["course_id"],
                "PageViews": n(s.get("page_views")),
                "MaxPageViews": n(s.get("max_page_views")),
                "PageViewsLevel": n(s.get("page_views_level")),
                "Participations": n(s.get("participations")),
                "MaxParticipations": n(s.get("max_participations")),
                "ParticipationsLevel": n(s.get("participations_level")),
                "MissingAssignments": n(tb.get("missing")),
                "LateAssignments": n(tb.get("late")),
                "OnTimeAssignments": n(tb.get("on_time")),
                "FloatingAssignments": n(tb.get("floating")),
            })
    enrollment = pd.DataFrame(enrollments)

    course_daily = [
        {"CourseId": c["course_id"], "Date": a["date"][:10], "Views": n(a.get("views")), "Participations": n(a.get("participations"))}
        for c in bundle["course_activity"]
        for a in c["activity"]
    ]

    dept = bundle["department"]
    account_daily = sorted(
        ({"Date": a["date"][:10], "Views": n(a.get("views")), "Participations": n(a.get("participations"))} for a in dept["activity"]["by_date"]),
        key=lambda r: r["Date"],
    )
    content_types = sorted(
        ({"ContentType": a["category"], "Views": n(a.get("views"))} for a in dept["activity"]["by_category"]),
        key=lambda r: -r["Views"],
    )

    stats = dept["statistics"]
    account_stats = [{
        "Term": term_name(bundle["sis_term_id"]),
        "DataAsOf": bundle["fetched_at"][:10],
        "AccountCourses": stats.get("courses"),
        "AccountTeachers": stats.get("teachers"),
        "AccountStudents": stats.get("students"),
        "AccountAssignments": stats.get("assignments"),
        "AccountDiscussionTopics": stats.get("discussion_topics"),
        "AccountAttachments": stats.get("attachments"),
        "AccountMediaObjects": stats.get("media_objects"),
        "OnlineCoursesMatched": bundle["matched_course_count"],
        "OnlineCoursesPulled": bundle["matched_course_count"] - bundle["failed_course_count"],
        "OnlineCoursesFailed": bundle["failed_course_count"],
    }]

    grades_path = Path(config.OUTPUT_DIR) / "dashboard_grades.json"
    grades = load_json(grades_path) if grades_path.exists() else EMPTY_GRADES

    return {
        "Dim_Course": pd.DataFrame(
            [{"CourseId": c["course_id"], "CourseCode": c.get("course_code"), "CourseName": c.get("name")} for c in summaries],
            columns=["CourseId", "CourseCode", "CourseName"],
        ),
        "Fact_Enrollment": enrollment,
        "Fact_CourseDailyActivity": pd.DataFrame(course_daily, columns=["CourseId", "Date", "Views", "Participations"]),
        "Fact_AccountDailyActivity": pd.DataFrame(account_daily, columns=["Date", "Views", "Participations"]),
        "Fact_ContentTypeViews": pd.DataFrame(content_types, columns=["ContentType", "Views"]),
        "Dim_FailedCourse": pd.DataFrame(
            [{"CourseId": f["course_id"], "CourseCode": f.get("course_code")} for f in bundle["failed_courses"]],
            columns=["CourseId", "CourseCode"],
        ),
        "Fact_AccountStatistics": pd.DataFrame(account_stats),
        "Dim_Student": (
            enrollment[["UserId", "UserName"]].drop_duplicates("UserId").sort_values("UserId")
            if not enrollment.empty else pd.DataFrame(columns=["UserId", "UserName"])
        ),
        "Fact_GradeDist_Summer2026": pd.DataFrame(
            [{"Grade": g["grade"], "Count": g["count"]} for g in grades["gradeDistribution"]],
            columns=["Grade", "Count"],
        ),
        "Fact_CourseGrades_Summer2026": pd.DataFrame(
            [{"CourseName": g["courseName"], "CourseId": g["courseId"], "AvgScore": g["avgScore"], "Students": g["students"]}
             for g in grades["courseGrades"]],
            columns=["CourseName", "CourseId", "AvgScore", "Students"],
        ),
    }


def build(bundle_path: Path) -> Path:
    bundle = load_json(bundle_path)
    tables = build_tables(bundle)

    dated_path = Path(config.OUTPUT_DIR) / f"canvas_pbi_model_{bundle['fetched_at'][:10]}.xlsx"
    dated_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(dated_path, engine="openpyxl") as writer:
        for sheet, df in tables.items():
            df.to_excel(writer, sheet_name=sheet, index=False)
    logger.info("Wrote Power BI model %s", dated_path)

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    export_path = EXPORT_DIR / EXPORT_NAME
    try:
        shutil.copyfile(dated_path, export_path)
    except PermissionError:
        logger.error("Could not overwrite %s — close it in Excel and rerun: python build_pbi_model.py %s", export_path, bundle_path)
        raise
    logger.info("Refreshed %s — open Analytics.pbix and click Refresh to load it.", export_path)
    return dated_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the Power BI source workbook from an analytics bundle.")
    parser.add_argument("bundle", type=Path, help="Path to analytics_bundle.json")
    args = parser.parse_args()
    build(args.bundle)


if __name__ == "__main__":
    main()
