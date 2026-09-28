# Canvas Engagement Pulse

Scripts that pull Canvas Analytics data for online/dual-enrollment courses
and feed the Canvas Engagement Pulse dashboard (`canvas_engagement_pulse_*.html`)
and the Power BI model (`canvas_pbi_model.xlsx`, built from this repo's parent
`canvas_pipeline` project).

This is a trimmed copy of the analytics-only scripts from
`C:\Canvas\Admin\Canvas Integration\canvas_pipeline` — the ValleyPROD/Oracle
SIS-provisioning pipeline (`transform.py`, `valleyprod.py`, `queries/`,
`pipeline.py`, `canvas_import.py`, `canvas_backfill.py`) was intentionally
left out. It isn't used to build analytics — it's a separate process that
syncs enrollments from the ValleyPROD Oracle database into Canvas via SIS
import, and has nothing to do with the Analytics API pull below.

## Setup

```
pip install -r requirements.txt
cp .env.example .env   # then fill in CANVAS_TOKEN
```

## Scripts

- `canvas_analytics_pull.py` — the main entry point. Pulls department and
  per-course Analytics API data for a term into `output/analytics/<term>/analytics_bundle.json`.
  Internally shells out to `canvas_terms.py` and `canvas_courses.py` as needed.
- `canvas_terms.py` — resolves/lists Canvas enrollment terms.
- `canvas_courses.py` — fetches the course list for a term.
- `canvas_users.py` — fetches all Canvas users to `output/canvas_users.json`
  (used to resolve student names for the at-risk roster).
- `config.py` — shared config/env loading.

## Requirements

Canvas admin API token only (`CANVAS_TOKEN` in `.env`). No database connection
is required for anything in this folder.
