r"""
build_dashboard.py — Render the Canvas Engagement Pulse dashboard from an
analytics_bundle.json written by canvas_analytics_pull.py.

canvas_analytics_pull.py calls this automatically at the end of every full
run. It can also be run on its own to rebuild from an existing bundle.

Usage:
    python build_dashboard.py output/analytics/202710/analytics_bundle.json

Inputs:
    dashboard_template.html     (tracked; __LIVE_DATA__ / __GRADES_DATA__ / __TERM_HTML__ placeholders)
    <bundle>                    (analytics_bundle.json)
    output/dashboard_grades.json (Summer 2026 grades block, carried over as-is —
                                  the live pull doesn't fetch the grades reference term)
    output/canvas_terms.json    (for the term display name)

Output:
    output/canvas_engagement_pulse_<YYYY-MM-DD>.html   (dated copy, kept)
    <DASHBOARD_EXPORT_DIR>/canvas_engagement_pulse.html (overwritten each run;
        default: ../dashboard_exports, override via DASHBOARD_EXPORT_DIR in .env)

At-risk scoring (per student x course enrollment):
    +2  zero page views
    +2  one or more missing assignments
    +1  zero participations
    Any enrollment scoring > 0 is listed as at-risk.
"""

import argparse
import datetime
import html
import json
import logging
import os
import shutil
from collections import defaultdict
from pathlib import Path

import config

logger = logging.getLogger(__name__)

HERE = Path(__file__).parent
TEMPLATE_PATH = HERE / "dashboard_template.html"
EXPORT_DIR = Path(os.environ.get("DASHBOARD_EXPORT_DIR", HERE.parent / "dashboard_exports"))
EXPORT_NAME = "canvas_engagement_pulse.html"

EMPTY_GRADES = {"gradeDistribution": [], "courseGrades": [], "fallFailRateSummer2026": None}


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def n(v) -> int:
    """Canvas returns null counts for students with no activity; treat as 0."""
    return v or 0


def term_name(sis_term_id: str) -> str:
    terms_path = Path(config.OUTPUT_DIR) / "canvas_terms.json"
    if terms_path.exists():
        for t in load_json(terms_path):
            if str(t.get("sis_term_id")) == str(sis_term_id):
                return t.get("name") or str(sis_term_id)
    return str(sis_term_id)


def student_names(bundle: dict) -> dict:
    """user id -> display name, from the per-course student rosters in the
    bundle, falling back to output/canvas_users.json if present."""
    names = {}
    users_path = Path(config.OUTPUT_DIR) / "canvas_users.json"
    if users_path.exists():
        names.update({u["id"]: u.get("name") for u in load_json(users_path)})
    for c in bundle.get("course_students", []):
        names.update({u["id"]: u.get("name") for u in c["students"]})
    return names


def build_live_data(bundle: dict) -> dict:
    names = student_names(bundle)
    activity_by_course = {c["course_id"]: c["activity"] for c in bundle["course_activity"]}

    courses = []
    risk_rows = []
    tracked_students = set()
    for c in bundle["course_student_summaries"]:
        cid = c["course_id"]
        summaries = c["student_summaries"]
        course_risk = 0
        for s in summaries:
            tracked_students.add(s["id"])
            tb = s.get("tardiness_breakdown") or {}
            page_views, participations = n(s.get("page_views")), n(s.get("participations"))
            zero_activity = page_views == 0
            has_missing = n(tb.get("missing")) > 0
            low_engagement = participations == 0
            score = 2 * zero_activity + 2 * has_missing + 1 * low_engagement
            if score == 0:
                continue
            course_risk += 1
            risk_rows.append({
                "userId": s["id"],
                "userName": names.get(s["id"]) or f"User {s['id']}",
                "courseId": cid,
                "courseCode": c.get("course_code"),
                "courseName": c.get("name"),
                "pageViews": page_views,
                "participations": participations,
                "pageViewsLevel": s.get("page_views_level"),
                "participationsLevel": s.get("participations_level"),
                "missingAssignments": n(tb.get("missing")),
                "lateAssignments": n(tb.get("late")),
                "onTimeAssignments": n(tb.get("on_time")),
                "riskScore": score,
                "zeroActivity": zero_activity,
                "hasMissing": has_missing,
                "lowEngagement": low_engagement,
            })

        activity = activity_by_course.get(cid, [])
        student_count = len(summaries)
        courses.append({
            "courseId": cid,
            "courseCode": c.get("course_code"),
            "courseName": c.get("name"),
            "views": sum(n(a.get("views")) for a in activity),
            "participations": sum(n(a.get("participations")) for a in activity),
            "studentCount": student_count,
            "atRiskStudents": course_risk,
            "engagementRate": round(100 * (student_count - course_risk) / student_count, 1) if student_count else 0.0,
        })
    courses.sort(key=lambda c: -c["views"])

    by_student = {}
    for r in risk_rows:
        st = by_student.setdefault(r["userId"], {
            "userId": r["userId"], "userName": r["userName"], "coursesAtRisk": 0,
            "totalRiskScore": 0, "zeroActivityCourses": 0, "missingAssignmentCourses": 0,
        })
        st["coursesAtRisk"] += 1
        st["totalRiskScore"] += r["riskScore"]
        st["zeroActivityCourses"] += r["zeroActivity"]
        st["missingAssignmentCourses"] += r["hasMissing"]
    risk_students = sorted(by_student.values(), key=lambda s: (-s["totalRiskScore"], -s["coursesAtRisk"], s["userName"]))

    daily = defaultdict(lambda: {"views": 0, "participations": 0})
    for activity in activity_by_course.values():
        for a in activity:
            day = a["date"][:10]
            daily[day]["views"] += n(a.get("views"))
            daily[day]["participations"] += n(a.get("participations"))

    dept_activity = bundle["department"]["activity"]
    stats = bundle["department"]["statistics"]
    return {
        "overview": {
            "term": term_name(bundle["sis_term_id"]),
            "dataAsOf": bundle["fetched_at"][:10],
            "source": "live",
            "accountCourses": stats.get("courses"),
            "accountTeachers": stats.get("teachers"),
            "accountStudents": stats.get("students"),
            "accountAssignments": stats.get("assignments"),
            "accountDiscussionTopics": stats.get("discussion_topics"),
            "accountAttachments": stats.get("attachments"),
            "accountTotalViews": sum(n(a.get("views")) for a in dept_activity["by_date"]),
            "accountTotalParticipations": sum(n(a.get("participations")) for a in dept_activity["by_date"]),
            "onlineCoursesMatched": bundle["matched_course_count"],
            "onlineCoursesPulled": bundle["matched_course_count"] - bundle["failed_course_count"],
            "onlineCoursesFailed": bundle["failed_course_count"],
            "onlineTotalViews": sum(c["views"] for c in courses),
            "onlineTotalParticipations": sum(c["participations"] for c in courses),
            "onlineStudentsTracked": len(tracked_students),
            "onlineAtRiskStudents": len(risk_students),
            "onlineAtRiskEnrollments": len(risk_rows),
        },
        "courses": courses,
        "contentTypes": sorted(
            ({"contentType": a["category"], "views": n(a.get("views"))} for a in dept_activity["by_category"]),
            key=lambda c: c["contentType"],
        ),
        "dailyActivity": [{"date": day, **daily[day]} for day in sorted(daily)],
        "deptDailyActivity": dept_activity["by_date"],
        "atRiskRows": risk_rows,
        "atRiskStudents": risk_students,
        "failedCourses": bundle["failed_courses"],
    }


def script_json(data) -> str:
    """JSON safe to embed inside a <script> element."""
    return json.dumps(data).replace("</", "<\\/")


def build(bundle_path: Path) -> Path:
    bundle = load_json(bundle_path)
    live = build_live_data(bundle)

    grades_path = Path(config.OUTPUT_DIR) / "dashboard_grades.json"
    if grades_path.exists():
        grades = load_json(grades_path)
    else:
        logger.warning("%s not found — Grades tab will be empty.", grades_path)
        grades = EMPTY_GRADES

    term_html = html.escape(live["overview"]["term"]).replace("-", "&ndash;")
    page = (
        TEMPLATE_PATH.read_text(encoding="utf-8")
        .replace("__LIVE_DATA__", script_json(live))
        .replace("__GRADES_DATA__", script_json(grades))
        .replace("__TERM_HTML__", term_html)
    )

    dated_path = Path(config.OUTPUT_DIR) / f"canvas_engagement_pulse_{live['overview']['dataAsOf']}.html"
    dated_path.parent.mkdir(parents=True, exist_ok=True)
    dated_path.write_text(page, encoding="utf-8")
    logger.info("Wrote dashboard %s", dated_path)

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    export_path = EXPORT_DIR / EXPORT_NAME
    shutil.copyfile(dated_path, export_path)
    logger.info("Refreshed %s", export_path)
    return dated_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the Canvas Engagement Pulse dashboard from an analytics bundle.")
    parser.add_argument("bundle", type=Path, help="Path to analytics_bundle.json")
    args = parser.parse_args()
    build(args.bundle)


if __name__ == "__main__":
    main()
