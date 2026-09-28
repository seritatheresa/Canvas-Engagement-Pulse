"""
canvas_courses.py — Fetch all courses for a Canvas enrollment term.

Writes results to a JSON file in the output directory.

Usage:
    python canvas_courses.py <sis_term_id>

    <sis_term_id> is the Banner term code (e.g. 202610).  The script
    resolves it to the Canvas internal term id by looking up
    output/canvas_terms.json (produced by canvas_terms.py).

Configuration is read from .env via config.py:
    CANVAS_URL          — e.g. https://mvsu.instructure.com
    CANVAS_TOKEN        — Canvas API access token
    CANVAS_ACCOUNT_ID   — account to query (default: 1)
    OUTPUT_DIR          — base output directory (default: ./output)
"""

import datetime
import json
import logging
import sys
import time
from pathlib import Path

import requests

import config

logger = logging.getLogger(__name__)


def resolve_term_id(sis_term_id: str) -> int:
    """Return the Canvas internal term id for the given sis_term_id.

    Reads output/canvas_terms.json (run canvas_terms.py first).
    Raises ValueError if the sis_term_id is not found.
    """
    terms_path = Path(config.OUTPUT_DIR) / "canvas_terms.json"
    if not terms_path.exists():
        raise FileNotFoundError(
            f"Terms file not found: {terms_path}\n"
            "Run canvas_terms.py first to generate it."
        )
    with open(terms_path) as f:
        terms = json.load(f)
    for term in terms:
        if str(term.get("sis_term_id")) == str(sis_term_id):
            return term["id"]
    raise ValueError(
        f"sis_term_id '{sis_term_id}' not found in {terms_path}.\n"
        "Check the value or re-run canvas_terms.py to refresh the list."
    )


def fetch_all_courses(enrollment_term_id: int) -> list:
    """Fetch every course for the given Canvas enrollment_term_id, handling pagination."""
    url = (
        f"{config.CANVAS_URL}/api/v1/accounts/{config.CANVAS_ACCOUNT_ID}/courses"
        f"?enrollment_term_id={enrollment_term_id}&include[]=syllabus_body"
    )
    headers = {"Authorization": f"Bearer {config.CANVAS_TOKEN}"}
    all_courses = []

    while url:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        all_courses.extend(response.json())
        url = response.links.get("next", {}).get("url")

    return all_courses


def save_to_json(data: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python canvas_courses.py <sis_term_id>")
        sys.exit(1)

    sis_term_id = sys.argv[1]

    try:
        enrollment_term_id = resolve_term_id(sis_term_id)
    except (FileNotFoundError, ValueError) as e:
        logger.error("%s", e)
        sys.exit(1)

    logger.info("Resolved sis_term_id=%s → Canvas id=%s", sis_term_id, enrollment_term_id)
    output_path = Path(config.OUTPUT_DIR) / f"canvas_courses_{sis_term_id}.json"

    start = time.time()
    try:
        courses = fetch_all_courses(enrollment_term_id)
        save_to_json(courses, output_path)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(
            "[%s] Saved %d courses to %s (%.2fs)",
            timestamp, len(courses), output_path, time.time() - start,
        )
    except requests.exceptions.HTTPError as e:
        logger.error("HTTP error: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
