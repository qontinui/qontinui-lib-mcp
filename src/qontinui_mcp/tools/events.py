"""Unified full-text search across qontinui-runner's Postgres event tables.

Wraps the `search_events` SQL query (see
`qontinui-runner/src-tauri/queries/event_search.sql`) that UNION ALLs across
`activity_timeline`, `observations`, `deferred_questions`, and `error_events`.

The Postgres URL comes from the `RUNNER_DATABASE_URL` env var (same name the
runner's Rust code reads in `main.rs`); if unset we fall back to the default
docker-compose credentials. A missing `psycopg` dependency is treated as a
user-facing error rather than a server-startup crash, so the MCP server can
still serve its other (SQLite-only) tools without the `events` extra
installed.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Schema-qualified table names are unnecessary because we SET search_path to
# runner,public — matching how the runner's own code accesses the tables
# (see proj_pg_dual_schema_runner_public in memory).
_SEARCH_PATH = "runner, public"

_DEFAULT_PG_URL = "postgres://qontinui_user:qontinui_dev_password" "@localhost:5432/qontinui_db"

# Query mirrors queries/event_search.sql. Kept inline (rather than read from
# disk) so the MCP package can ship independently of the runner checkout.
# ruff: noqa: E501 — SQL lines are deliberately long for readability.
_SEARCH_EVENTS_SQL = """
WITH q AS (
    SELECT plainto_tsquery('english', %(query_text)s) AS tsq,
           %(since_ts)s::timestamptz AS since_ts,
           %(max_results)s::bigint AS max_rows
)
SELECT source_table, record_id, snippet, event_ts, score
FROM (
    SELECT
        'activity_timeline'::text AS source_table,
        at.id::text AS record_id,
        LEFT(at.text_content, 400) AS snippet,
        at.created_at AS event_ts,
        ts_rank_cd(to_tsvector('english', at.text_content), q.tsq)::float4 AS score
    FROM activity_timeline at, q
    WHERE to_tsvector('english', at.text_content) @@ q.tsq
      AND at.created_at >= q.since_ts
      AND NOT at.is_deleted

    UNION ALL
    SELECT
        'observations'::text,
        o.id::text,
        LEFT(o.title || ' — ' || o.content, 400),
        o.created_at,
        ts_rank_cd(to_tsvector('english', o.title || ' ' || o.content), q.tsq)::float4
    FROM observations o, q
    WHERE to_tsvector('english', o.title || ' ' || o.content) @@ q.tsq
      AND o.created_at >= q.since_ts
      AND NOT o.is_deleted

    UNION ALL
    SELECT
        'deferred_questions'::text,
        dq.id,
        LEFT(dq.question, 400),
        dq.created_at,
        ts_rank_cd(
            to_tsvector('english', dq.question || ' ' || COALESCE(dq.context_json, '')),
            q.tsq
        )::float4
    FROM deferred_questions dq, q
    WHERE to_tsvector('english', dq.question || ' ' || COALESCE(dq.context_json, '')) @@ q.tsq
      AND dq.created_at >= q.since_ts

    UNION ALL
    SELECT
        'error_events'::text,
        ee.id::text,
        LEFT(ee.message, 400),
        ee.captured_at,
        ts_rank_cd(
            to_tsvector(
                'english',
                ee.message || ' ' || COALESCE(ee.stack_trace, '') || ' ' || COALESCE(ee.context_lines, '')
            ),
            q.tsq
        )::float4
    FROM error_events ee, q
    WHERE to_tsvector(
            'english',
            ee.message || ' ' || COALESCE(ee.stack_trace, '') || ' ' || COALESCE(ee.context_lines, '')
          ) @@ q.tsq
      AND ee.captured_at >= q.since_ts
) sub
ORDER BY score DESC, event_ts DESC
LIMIT (SELECT max_rows FROM q);
"""


def _resolve_since(since_iso: str | None) -> datetime:
    """Parse an ISO-8601 timestamp or fall back to 7 days ago (UTC)."""
    if since_iso:
        # Support both "...Z" and "+00:00" suffixes.
        iso = since_iso.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(iso)
        except ValueError as exc:
            raise ValueError(
                f"Invalid since_iso (expected ISO-8601): {since_iso!r} ({exc})"
            ) from exc
        if parsed.tzinfo is None:
            # Naive datetimes are interpreted as UTC to match runner semantics.
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return datetime.now(timezone.utc) - timedelta(days=7)


def _resolve_pg_url() -> str:
    # Accept both the runner-internal env name and a generic DATABASE_URL as
    # a fallback, preferring the runner-specific one.
    return (
        os.environ.get("RUNNER_DATABASE_URL") or os.environ.get("DATABASE_URL") or _DEFAULT_PG_URL
    )


def search_events(
    query: str,
    since_iso: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search across activity_timeline / observations / deferred_questions /
    error_events for rows whose FTS tsvector matches `query`.

    Args:
        query: Free-text query passed through `plainto_tsquery('english', …)`.
        since_iso: Lower bound on the event timestamp (ISO-8601). Defaults to
            7 days before now (UTC).
        limit: Maximum number of rows to return.

    Returns:
        A list of dicts with keys: source_table, record_id, snippet, ts,
        score. Sorted by score desc, then ts desc.

    Raises:
        RuntimeError: if `psycopg` is not installed (the `events` extra).
        ValueError: if `since_iso` is malformed.
    """
    if not query or not query.strip():
        raise ValueError("query must be a non-empty string")

    try:
        import psycopg  # type: ignore[import-not-found]  # noqa: PLC0415 — import-on-demand is intentional
    except ImportError as exc:
        raise RuntimeError(
            "search_events requires psycopg. Install the 'events' extra: "
            "`pip install qontinui-mcp[events]` (or `poetry install --extras events`)."
        ) from exc

    since_ts = _resolve_since(since_iso)
    pg_url = _resolve_pg_url()

    # Clamp limit to something sensible; the UNION ALL can be expensive if
    # callers pass huge limits.
    lim = max(1, min(int(limit), 500))

    rows: list[dict[str, Any]] = []
    with psycopg.connect(pg_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SET search_path TO {_SEARCH_PATH}")
            cur.execute(
                _SEARCH_EVENTS_SQL,
                {
                    "query_text": query,
                    "since_ts": since_ts,
                    "max_results": lim,
                },
            )
            for source_table, record_id, snippet, event_ts, score in cur:
                rows.append(
                    {
                        "source_table": source_table,
                        "record_id": record_id,
                        "snippet": snippet,
                        "ts": event_ts.isoformat() if event_ts else None,
                        "score": float(score) if score is not None else 0.0,
                    }
                )
    return rows
