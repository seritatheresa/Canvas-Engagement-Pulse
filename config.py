"""
config.py - Central configuration loader.

Reads all settings from environment variables (loaded from a .env file
if python-dotenv is installed). Every other module imports from here --
no credentials ever appear in source code.
"""

import os
import logging
from pathlib import Path

_ENV_FILE = Path(__file__).parent / ".env"

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_ENV_FILE, override=True)
except ImportError:
    pass


def _require(key):
    value = os.environ.get(key)
    if not value:
        raise EnvironmentError(
            "Required environment variable '{}' is not set. "
            "Copy .env.example to .env and fill in your values.".format(key)
        )
    return value


# -- ValleyPROD Oracle (python-oracledb thin mode — no Oracle Client required) --
# These are read lazily so that Canvas-only scripts (canvas_terms.py, etc.)
# can import config without requiring Oracle credentials in the environment.
VALLEYPROD_HOST         = os.environ.get("VALLEYPROD_HOST", "")
VALLEYPROD_PORT         = os.environ.get("VALLEYPROD_PORT", "1521")
VALLEYPROD_SERVICE      = os.environ.get("VALLEYPROD_SERVICE", "")
VALLEYPROD_USER         = os.environ.get("VALLEYPROD_USER", "")
VALLEYPROD_PASSWORD     = os.environ.get("VALLEYPROD_PASSWORD", "")


def require_oracle_config() -> None:
    """Raise EnvironmentError if any Oracle credential is missing.
    Call this at the top of any module that needs a database connection."""
    for key in ("VALLEYPROD_HOST", "VALLEYPROD_SERVICE", "VALLEYPROD_USER", "VALLEYPROD_PASSWORD"):
        _require(key)

# -- Canvas LMS ----------------------------------------------------------------
CANVAS_URL              = _require("CANVAS_URL").rstrip("/")
CANVAS_TOKEN            = _require("CANVAS_TOKEN")
CANVAS_ACCOUNT_ID       = os.environ.get("CANVAS_ACCOUNT_ID", "1")
CANVAS_AUTH_PROVIDER_ID = os.environ.get("CANVAS_AUTH_PROVIDER_ID", "108")

# -- Pipeline behaviour --------------------------------------------------------
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "./output")
LOG_LEVEL  = os.environ.get("LOG_LEVEL", "INFO").upper()

# -- Logging setup (called once at import time) --------------------------------
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
