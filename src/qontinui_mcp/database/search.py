"""Full-text search using SQLite FTS5."""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

Row = dict[str, Any]


def search_nodes(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[Row]:
    """Search for nodes using FTS5."""
    logger.debug(f"Searching nodes for: {query}")

    fts_query = _prepare_fts_query(query)

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            n.*,
            nf.rank as search_rank,
            highlight(nodes_fts, 1, '<mark>', '</mark>') as highlighted_name,
            highlight(nodes_fts, 3, '<mark>', '</mark>') as highlighted_description
        FROM nodes_fts nf
        JOIN nodes n ON nf.rowid = n.rowid
        WHERE nodes_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (fts_query, limit),
    )

    rows = cursor.fetchall()
    results = []

    for row in rows:
        node = _parse_node_row(row)
        rank = row["search_rank"]

        # Determine which fields matched
        matched_fields = []
        highlighted_name = row["highlighted_name"] or ""
        highlighted_description = row["highlighted_description"] or ""

        if "<mark>" in highlighted_name:
            matched_fields.append("name")
        if "<mark>" in highlighted_description:
            matched_fields.append("description")

        results.append(
            {
                "node": node,
                "score": abs(rank),  # FTS5 rank is negative, lower is better
                "matched_fields": matched_fields,
            }
        )

    return results


def search_workflows(
    conn: sqlite3.Connection, query: str, limit: int = 10
) -> list[Row]:
    """Search for workflows using FTS5."""
    logger.debug(f"Searching workflows for: {query}")

    fts_query = _prepare_fts_query(query)

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            w.*,
            wf.rank as search_rank,
            highlight(workflows_fts, 1, '<mark>', '</mark>') as highlighted_name,
            highlight(workflows_fts, 3, '<mark>', '</mark>') as highlighted_description
        FROM workflows_fts wf
        JOIN workflows w ON wf.rowid = w.rowid
        WHERE workflows_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (fts_query, limit),
    )

    rows = cursor.fetchall()
    results = []

    for row in rows:
        workflow = _parse_workflow_row(row)
        rank = row["search_rank"]

        matched_fields = []
        highlighted_name = row["highlighted_name"] or ""
        highlighted_description = row["highlighted_description"] or ""

        if "<mark>" in highlighted_name:
            matched_fields.append("name")
        if "<mark>" in highlighted_description:
            matched_fields.append("description")

        results.append(
            {
                "workflow": workflow,
                "score": abs(rank),
                "matched_fields": matched_fields,
            }
        )

    return results


def search_nodes_by_category(conn: sqlite3.Connection, category: str) -> list[Row]:
    """Search nodes by category."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM nodes WHERE category = ? ORDER BY name",
        (category,),
    )
    rows = cursor.fetchall()
    return [_parse_node_row(row) for row in rows]


def search_workflows_by_category(conn: sqlite3.Connection, category: str) -> list[Row]:
    """Search workflows by category."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM workflows WHERE category = ? ORDER BY name",
        (category,),
    )
    rows = cursor.fetchall()
    return [_parse_workflow_row(row) for row in rows]


def search_nodes_by_action_type(
    conn: sqlite3.Connection, action_type: str
) -> list[Row]:
    """Search nodes by action type."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM nodes WHERE action_type = ? ORDER BY name",
        (action_type,),
    )
    rows = cursor.fetchall()
    return [_parse_node_row(row) for row in rows]


def get_all_categories(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Get all categories."""
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT category FROM nodes ORDER BY category")
    node_categories = [row["category"] for row in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT category FROM workflows ORDER BY category")
    workflow_categories = [row["category"] for row in cursor.fetchall()]

    return {
        "nodes": node_categories,
        "workflows": workflow_categories,
    }


def _prepare_fts_query(query: str) -> str:
    """Prepare FTS5 query by escaping special characters and handling phrases."""
    # Remove special FTS5 characters that could cause syntax errors
    cleaned = query.replace('"', " ").replace("*", " ")

    # Split into words
    words = [w for w in cleaned.split() if w]

    if not words:
        return '""'  # Empty query

    # If single word, use prefix matching
    if len(words) == 1:
        return f"{words[0]}*"

    # For multiple words, use OR matching with prefix
    return " OR ".join(f"{w}*" for w in words)


def _parse_node_row(row: sqlite3.Row) -> Row:
    """Parse node row from database."""
    return {
        "id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "description": row["description"],
        "action_type": row["action_type"],
        "parameters": json.loads(row["parameters"]),
        "examples": json.loads(row["examples"] or "[]"),
        "tags": json.loads(row["tags"] or "[]"),
    }


def _parse_workflow_row(row: sqlite3.Row) -> Row:
    """Parse workflow row from database."""
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "category": row["category"],
        "tags": json.loads(row["tags"]),
        "complexity": row["complexity"],
        "template": json.loads(row["template"]),
        "use_cases": json.loads(row["use_cases"]),
        "customization_points": json.loads(row["customization_points"]),
    }
