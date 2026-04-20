"""Database loader - loads node and workflow data into SQLite."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qontinui_mcp.types import NodeMetadata, WorkflowTemplate

logger = logging.getLogger(__name__)


def initialize_database(db_path: str) -> sqlite3.Connection:
    """Initialize the database with schema."""
    logger.info(f"Initializing database at {db_path}")

    # Ensure parent directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Read and execute schema
    schema_path = Path(__file__).parent / "schema.sql"
    schema = schema_path.read_text()

    # Execute schema (SQLite handles multiple statements with executescript)
    conn.executescript(schema)
    conn.commit()

    logger.info("Database schema initialized")
    return conn


def load_nodes(conn: sqlite3.Connection, nodes: list[NodeMetadata]) -> None:
    """Load nodes into the database."""
    cursor = conn.cursor()

    for node in nodes:
        cursor.execute(
            """
            INSERT OR REPLACE INTO nodes
            (id, name, category, description, action_type, parameters, examples, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node.id,
                node.name,
                node.category,
                node.description,
                (
                    node.action_type.value
                    if hasattr(node.action_type, "value")
                    else node.action_type
                ),
                json.dumps([p.model_dump() for p in node.parameters]),
                json.dumps(node.examples or []),
                json.dumps(node.tags or []),
            ),
        )

    conn.commit()
    logger.info(f"Loaded {len(nodes)} nodes into database")


def load_workflows(conn: sqlite3.Connection, workflows: list[WorkflowTemplate]) -> None:
    """Load workflows into the database."""
    cursor = conn.cursor()

    for workflow in workflows:
        cursor.execute(
            """
            INSERT OR REPLACE INTO workflows
            (id, name, description, category, tags, complexity,
             template, use_cases, customization_points)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow.id,
                workflow.name,
                workflow.description,
                workflow.category,
                json.dumps(workflow.tags),
                workflow.complexity,
                json.dumps(workflow.template.model_dump()),
                json.dumps(workflow.use_cases),
                json.dumps(workflow.customization_points),
            ),
        )

    conn.commit()
    logger.info(f"Loaded {len(workflows)} workflows into database")


def get_node(conn: sqlite3.Connection, node_id: str) -> dict[str, Any] | None:
    """Get node by ID."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
    row = cursor.fetchone()

    if not row:
        return None

    return _parse_node_row(row)


def get_workflow(conn: sqlite3.Connection, workflow_id: str) -> dict[str, Any] | None:
    """Get workflow by ID."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
    row = cursor.fetchone()

    if not row:
        return None

    return _parse_workflow_row(row)


def get_all_nodes(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Get all nodes."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM nodes ORDER BY category, name")
    rows = cursor.fetchall()
    return [_parse_node_row(row) for row in rows]


def get_all_workflows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Get all workflows."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM workflows ORDER BY category, name")
    rows = cursor.fetchall()
    return [_parse_workflow_row(row) for row in rows]


def _parse_node_row(row: sqlite3.Row) -> dict[str, Any]:
    """Parse a node row from database."""
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


def _parse_workflow_row(row: sqlite3.Row) -> dict[str, Any]:
    """Parse a workflow row from database."""
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
