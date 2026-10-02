"""
canvas_terms.py — Fetch all active enrollment terms from Canvas.

Writes results to a JSON file in the output directory.

Usage:
    python canvas_terms.py

Configuration is read from .env via config.py:
    CANVAS_URL        — e.g. https://mvsu.instructure.com
    CANVAS_TOKEN      — Canvas API access token
    CANVAS_ACCOUNT_ID — account to query (default: 1)
    OUTPUT_DIR        — base output directory (default: ./output)
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


def fetch_active_terms() -> list:
    """Fetch all active enrollment terms for the account, handling pagination."""
    url = (
        f"{config.CANVAS_URL}/api/v1/accounts/{config.CANVAS_ACCOUNT_ID}/terms"
        "?workflow_state=active"
    )
    headers = {"Authorization": f"Bearer {config.CANVAS_TOKEN}"}
    all_terms = []

    while url:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        all_terms.extend(response.json().get("enrollment_terms", []))
        url = response.links.get("next", {}).get("url")

    return all_terms


def save_to_json(data: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


def main() -> None:
    output_path = Path(config.OUTPUT_DIR) / "canvas_terms.json"

    start = time.time()
    try:
        terms = fetch_active_terms()
        save_to_json(terms, output_path)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(
            "[%s] Saved %d active terms to %s (%.2fs)",
            timestamp, len(terms), output_path, time.time() - start,
        )
        for term in terms:
            logger.info("  id=%-5s  sis_id=%-12s  %s", term.get("id"), term.get("sis_term_id"), term.get("name"))
    except requests.exceptions.HTTPError as e:
        logger.error("HTTP error: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
