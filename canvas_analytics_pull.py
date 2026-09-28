r"""
canvas_analytics_pull.py — Fetch live Canvas Analytics data for online/dual-enrollment
courses and write it to JSON for the Canvas Engagement Pulse dashboard.

Written to match the conventions of canvas_users.py / canvas_courses.py in this
pipeline (same config.py, same pagination pattern via response.links, same
logging/argparse style) so it fits alongside the existing provisioning scripts.

WHY THIS RUNS HERE, NOT FROM CLAUDE:
Claude's cloud/device shell traffic is routed through an organization egress
proxy that does not currently allow mvsu.instructure.com, so Claude can't
execute this script itself. Run it yourself from a normal terminal on a
machine with real network access to Canvas (the same one the rest of this
pipeline already uses), then hand the resulting JSON file back to Claude to
merge into the dashboard.

What it fetches (Canvas Analytics API — see
https://developerdocs.instructure.com/services/canvas/resources/analytics):

  Department-level (whole account, one call each):
    - GET /accounts/:id/analytics/terms/:term_id/activity
    - GET /accounts/:id/analytics/terms/:term_id/grades
    - GET /accounts/:id/analytics/terms/:term_id/statistics

  Course-level (one call each, per matched course):
    - GET /courses/:id/analytics/activity
    - GET /courses/:id/analytics/student_summaries

Course selection: online / dual-enrollment sections only — course_code or
name contains "E0<digit>" (e.g. "E01", "E02" — MVSU's online section suffix)
or "DE" (dual enrollment), matching the filter used in the existing
Canvas Engagement Pulse dashboard build.

Usage:
    python canvas_analytics_pull.py --sis-term-id 202710
    python canvas_analytics_pull.py --sis-term-id 202710 --pattern "E0\d|DE"
    python canvas_analytics_pull.py --sis-term-id 202710 --course-list-only   # dry run, no analytics calls

Requires output/canvas_terms.json and output/canvas_courses_<sis_term_id>.json
to already exist (run canvas_terms.py and canvas_courses.py <sis_term_id> first,
or this script will fetch/refresh both automatically).

Configuration is read from .env via config.py (same CANVAS_URL / CANVAS_TOKEN /
CANVAS_ACCOUNT_ID used by the rest of this pipeline).

Output:
    output/analytics/<sis_term_id>/department_activity.json
    output/analytics/<sis_term_id>/department_grades.json
    output/analytics/<sis_term_id>/department_statistics.json
    output/analytics/<sis_term_id>/course_activity.json         (list, one entry per matched course)
    output/analytics/<sis_term_id>/course_student_summaries.json (list, one entry per matched course)
    output/analytics/<sis_term_id>/matched_courses.json          (the course list used)
    output/analytics/<sis_term_id>/analytics_bundle.json         (everything above, combined — hand this one to Claude)
"""

import argparse
import datetime
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

import config

logger = logging.getLogger(__name__)

DEFAULT_PATTERN = r"(E0\d|DE)"


def load_json(path: Path):
    with open(path) as f:
        return json.load(f)


def save_json(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def ensure_terms_and_courses(sis_term_id: str) -> tuple[Path, Path]:
    """Make sure canvas_terms.json and canvas_courses_<sis_term_id>.json exist,
    fetching them via the sibling scripts if not."""
    output_dir = Path(config.OUTPUT_DIR)
    terms_path = output_dir / "canvas_terms.json"
    courses_path = output_dir / f"canvas_courses_{sis_term_id}.json"

    if not terms_path.exists():
        logger.info("canvas_terms.json not found — running canvas_terms.py")
        subprocess.run([sys.executable, "canvas_terms.py"], check=True)

    if not courses_path.exists():
        logger.info("%s not found — running canvas_courses.py %s", courses_path.name, sis_term_id)
        subprocess.run([sys.executable, "canvas_courses.py", sis_term_id], check=True)

    return terms_path, courses_path


def resolve_term_id(sis_term_id: str, terms_path: Path) -> int:
    terms = load_json(terms_path)
    for t in terms:
        if str(t.get("sis_term_id")) == str(sis_term_id):
            return t["id"]
    raise ValueError(f"sis_term_id '{sis_term_id}' not found in {terms_path}.")


def select_online_courses(courses_path: Path, pattern: str) -> list:
    """Filter the term's course list down to online / dual-enrollment sections
    by course_code or name (e.g. 'CJ 593 E01', 'HI 215 DE01')."""
    rx = re.compile(pattern, re.IGNORECASE)
    courses = load_json(courses_path)
    matched = [
        c for c in courses
        if rx.search(c.get("course_code", "") or "") or rx.search(c.get("name", "") or "")
    ]
    return matched


def get_paginated(url: str, headers: dict) -> list:
    all_items = []
    while url:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        all_items.extend(response.json())
        url = response.links.get("next", {}).get("url")
    return all_items


def fetch_department_analytics(enrollment_term_id: int, headers: dict) -> dict:
    base = f"{config.CANVAS_URL}/api/v1/accounts/{config.CANVAS_ACCOUNT_ID}/analytics/terms/{enrollment_term_id}"

    logger.info("Fetching department-level activity…")
    activity = requests.get(f"{base}/activity", headers=headers)
    activity.raise_for_status()

    logger.info("Fetching department-level grade distribution…")
    grades = requests.get(f"{base}/grades", headers=headers)
    grades.raise_for_status()

    logger.info("Fetching department-level statistics…")
    stats = requests.get(f"{base}/statistics", headers=headers)
    stats.raise_for_status()

    return {
        "activity": activity.json(),
        "grades": grades.json(),
        "statistics": stats.json(),
    }


def fetch_course_analytics(course_id: int, headers: dict) -> dict:
    """One course's activity + student_summaries. Each is a single call
    (not paginated in practice for a normal course roster size, but we
    still honor pagination in case a huge section spans pages)."""
    activity_url = f"{config.CANVAS_URL}/api/v1/courses/{course_id}/analytics/activity"
    summaries_url = f"{config.CANVAS_URL}/api/v1/courses/{course_id}/analytics/student_summaries"

    activity = get_paginated(activity_url, headers)
    summaries = get_paginated(summaries_url, headers)

    return {"course_id": course_id, "activity": activity, "student_summaries": summaries}


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull live Canvas Analytics data for online/DE courses.")
    parser.add_argument("--sis-term-id", required=True, help="Banner term code, e.g. 202710")
    parser.add_argument(
        "--pattern", default=DEFAULT_PATTERN,
        help=r"Regex used against course_code/name to select online/DE sections (default: E0\d or DE)",
    )
    parser.add_argument(
        "--course-list-only", action="store_true",
        help="Only resolve and print the matched course list — skip all analytics API calls.",
    )
    parser.add_argument(
        "--sleep", type=float, default=0.25,
        help="Seconds to sleep between course-level API calls, to stay polite to Canvas (default: 0.25).",
    )
    args = parser.parse_args()

    terms_path, courses_path = ensure_terms_and_courses(args.sis_term_id)
    enrollment_term_id = resolve_term_id(args.sis_term_id, terms_path)
    logger.info("Resolved sis_term_id=%s -> Canvas enrollment_term_id=%s", args.sis_term_id, enrollment_term_id)

    matched = select_online_courses(courses_path, args.pattern)
    logger.info("Matched %d online/DE courses out of the term's full course list", len(matched))

    out_dir = Path(config.OUTPUT_DIR) / "analytics" / args.sis_term_id
    save_json(
        [{"id": c["id"], "course_code": c.get("course_code"), "name": c.get("name")} for c in matched],
        out_dir / "matched_courses.json",
    )

    if args.course_list_only:
        for c in matched:
            print(f"{c['id']}\t{c.get('course_code')}\t{c.get('name')}")
        logger.info("Course-list-only run — wrote %s, no analytics calls made.", out_dir / "matched_courses.json")
        return

    headers = {"Authorization": f"Bearer {config.CANVAS_TOKEN}"}
    start = time.time()

    dept = fetch_department_analytics(enrollment_term_id, headers)
    save_json(dept["activity"], out_dir / "department_activity.json")
    save_json(dept["grades"], out_dir / "department_grades.json")
    save_json(dept["statistics"], out_dir / "department_statistics.json")

    course_activity = []
    course_summaries = []
    failed = []
    for i, c in enumerate(matched, start=1):
        cid = c["id"]
        logger.info("[%d/%d] course %s — %s (%s)", i, len(matched), cid, c.get("course_code"), c.get("name"))
        try:
            result = fetch_course_analytics(cid, headers)
            course_activity.append({"course_id": cid, "course_code": c.get("course_code"), "name": c.get("name"), "activity": result["activity"]})
            course_summaries.append({"course_id": cid, "course_code": c.get("course_code"), "name": c.get("name"), "student_summaries": result["student_summaries"]})
        except requests.exceptions.HTTPError as e:
            logger.warning("  failed for course %s: %s", cid, e)
            failed.append({"course_id": cid, "course_code": c.get("course_code"), "error": str(e)})
        time.sleep(args.sleep)

    save_json(course_activity, out_dir / "course_activity.json")
    save_json(course_summaries, out_dir / "course_student_summaries.json")

    bundle = {
        "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "sis_term_id": args.sis_term_id,
        "enrollment_term_id": enrollment_term_id,
        "pattern": args.pattern,
        "matched_course_count": len(matched),
        "failed_course_count": len(failed),
        "failed_courses": failed,
        "department": dept,
        "course_activity": course_activity,
        "course_student_summaries": course_summaries,
    }
    save_json(bundle, out_dir / "analytics_bundle.json")

    logger.info(
        "Done in %.1fs — %d/%d courses pulled successfully. Send %s to Claude to merge into the dashboard.",
        time.time() - start, len(matched) - len(failed), len(matched), out_dir / "analytics_bundle.json",
    )


if __name__ == "__main__":
    main()
