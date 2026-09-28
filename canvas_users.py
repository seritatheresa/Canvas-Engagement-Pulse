"""
canvas_users.py — Fetch all users from Canvas.

Writes results to a JSON file in the output directory.  Because a full
fetch can take several minutes, the script skips the fetch when the output
file is younger than --max-age-days (default: 7).  Use --force to always
re-fetch regardless of file age.

Usage:
    python canvas_users.py                  # skip if file < 7 days old
    python canvas_users.py --force          # always re-fetch
    python canvas_users.py --max-age-days 1 # re-fetch if file is > 1 day old

Configuration is read from .env via config.py:
    CANVAS_URL          — e.g. https://mvsu.instructure.com
    CANVAS_TOKEN        — Canvas API access token
    CANVAS_ACCOUNT_ID   — account to query (default: 1)
    OUTPUT_DIR          — base output directory (default: ./output)
"""

import argparse
import datetime
import json
import logging
import sys
import time
from pathlib import Path

import requests

import config

logger = logging.getLogger(__name__)

DEFAULT_MAX_AGE_DAYS = 7


def file_age_days(path: Path) -> float | None:
    """Return the age of *path* in days, or None if the file doesn't exist."""
    if not path.exists():
        return None
    age_seconds = time.time() - path.stat().st_mtime
    return age_seconds / 86400


def fetch_all_users() -> list:
    """Fetch every user in the Canvas account, handling pagination."""
    url = f"{config.CANVAS_URL}/api/v1/accounts/{config.CANVAS_ACCOUNT_ID}/users"
    headers = {"Authorization": f"Bearer {config.CANVAS_TOKEN}"}
    all_users = []

    while url:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        all_users.extend(response.json())
        url = response.links.get("next", {}).get("url")

    return all_users


def save_to_json(data: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Canvas users to canvas_users.json")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch even if canvas_users.json is still fresh.",
    )
    parser.add_argument(
        "--max-age-days",
        type=float,
        default=DEFAULT_MAX_AGE_DAYS,
        metavar="N",
        help=f"Skip fetch if the output file is younger than N days (default: {DEFAULT_MAX_AGE_DAYS}).",
    )
    args = parser.parse_args()

    output_path = Path(config.OUTPUT_DIR) / "canvas_users.json"

    if not args.force:
        age = file_age_days(output_path)
        if age is not None and age < args.max_age_days:
            modified = datetime.datetime.fromtimestamp(output_path.stat().st_mtime)
            logger.info(
                "canvas_users.json is %.1f day(s) old (last fetched %s) — skipping fetch. "
                "Use --force to re-fetch.",
                age,
                modified.strftime("%Y-%m-%d %H:%M"),
            )
            return

    start = time.time()
    try:
        users = fetch_all_users()
        save_to_json(users, output_path)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(
            "[%s] Saved %d users to %s (%.2fs)",
            timestamp, len(users), output_path, time.time() - start,
        )
    except requests.exceptions.HTTPError as e:
        logger.error("HTTP error: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
