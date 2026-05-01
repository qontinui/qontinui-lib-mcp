"""Qontinui MCP Server Implementation.

Provides AI-powered workflow generation, node discovery, and automation execution.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from qontinui_mcp.database.loader import get_node, initialize_database
from qontinui_mcp.database.search import (
    get_all_categories,
    search_nodes,
    search_nodes_by_action_type,
    search_nodes_by_category,
    search_workflows,
)
from qontinui_mcp.tools.events import search_events
from qontinui_mcp.tools.execution import (
    assert_state_visible,
    capture_checkpoint,
    capture_screen,
    compare_screenshots,
    is_execution_available,
    run_automation,
    wait_for_state,
)
from qontinui_mcp.tools.expectations import (
    evaluate_checkpoint,
    evaluate_workflow_expectations,
    validate_expectations_config,
)
from qontinui_mcp.tools.generator import WorkflowGenerator
from qontinui_mcp.types.models import CheckpointDefinition
from qontinui_mcp.utils.validation import validate_workflow_structure

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database path
DB_DIR = Path.home() / ".qontinui" / "mcp"
DB_PATH = DB_DIR / "qontinui.db"


def get_db_connection() -> sqlite3.Connection:
    """Get database connection, initializing if needed."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return initialize_database(str(DB_PATH))


# Initialize MCP server
server = Server("qontinui-mcp")


@server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
async def list_tools() -> list[Tool]:
    """List all available tools."""
    tools = [
        # Knowledge/Search Tools
        Tool(
            name="search_nodes",
            description="Search for Qontinui action nodes using natural language. Returns matching nodes with descriptions and parameters.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'click button', 'find image', 'type text')",
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of results (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="search_workflows",
            description="Search for Qontinui workflow templates using natural language. Returns matching workflow templates with use cases.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'login workflow', 'data entry', 'form filling')",
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of results (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_nodes_by_category",
            description="Get all nodes in a specific category (e.g., 'mouse', 'keyboard', 'vision').",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Category name",
                    },
                },
                "required": ["category"],
            },
        ),
        Tool(
            name="get_nodes_by_action_type",
            description="Get all nodes of a specific action type (e.g., 'CLICK', 'FIND', 'TYPE').",
            inputSchema={
                "type": "object",
                "properties": {
                    "action_type": {
                        "type": "string",
                        "description": "Action type (e.g., CLICK, FIND, TYPE)",
                    },
                },
                "required": ["action_type"],
            },
        ),
        Tool(
            name="list_categories",
            description="List all available categories for nodes and workflows.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_action_details",
            description="Get detailed information about a specific action node including parameters, examples, and usage.",
            inputSchema={
                "type": "object",
                "properties": {
                    "action_id": {
                        "type": "string",
                        "description": "The ID of the action node",
                    },
                },
                "required": ["action_id"],
            },
        ),
        # Workflow Tools
        Tool(
            name="validate_workflow",
            description="Validate a workflow JSON structure. Checks schema, connections, detects cycles, and finds unreachable steps.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow": {
                        "type": "object",
                        "description": "The workflow JSON to validate",
                    },
                },
                "required": ["workflow"],
            },
        ),
        Tool(
            name="create_workflow",
            description="Create a workflow from a list of action steps. Automatically generates UUIDs and connections.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the workflow",
                    },
                    "description": {
                        "type": "string",
                        "description": "Description of what the workflow does",
                    },
                    "steps": {
                        "type": "array",
                        "description": "Array of workflow steps",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "description": "Action type (e.g., CLICK, FIND, TYPE)",
                                },
                                "description": {
                                    "type": "string",
                                    "description": "Step description",
                                },
                                "options": {
                                    "type": "object",
                                    "description": "Action options",
                                },
                            },
                            "required": ["action"],
                        },
                    },
                },
                "required": ["name", "description", "steps"],
            },
        ),
        Tool(
            name="generate_workflow",
            description="Generate a complete workflow from a natural language description. AI-powered workflow creation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Natural language description of the workflow (e.g., 'Login to website by clicking login button and typing credentials')",
                    },
                },
                "required": ["description"],
            },
        ),
        # Execution Tools
        Tool(
            name="run_automation",
            description="Execute a Qontinui automation script and return results. Optionally evaluates expectations after execution. Requires qontinui library.",
            inputSchema={
                "type": "object",
                "properties": {
                    "script": {
                        "type": "string",
                        "description": "The automation script in DSL format or JSON workflow",
                    },
                    "timeout_seconds": {
                        "type": "number",
                        "description": "Maximum execution time in seconds (default: 30)",
                        "default": 30,
                    },
                    "capture_screenshot": {
                        "type": "boolean",
                        "description": "Whether to capture final screenshot (default: true)",
                        "default": True,
                    },
                    "expectations": {
                        "type": "object",
                        "description": "Optional workflow expectations to evaluate after execution (global settings, success criteria, checkpoints)",
                    },
                    "workflow_id": {
                        "type": "string",
                        "description": "Optional workflow ID for expectations evaluation",
                    },
                },
                "required": ["script"],
            },
        ),
        Tool(
            name="capture_screenshot",
            description="Capture the current screen and return as base64-encoded image.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="assert_state_visible",
            description="Assert that a visual state/element is visible on screen. Returns match confidence and location.",
            inputSchema={
                "type": "object",
                "properties": {
                    "state_image_path": {
                        "type": "string",
                        "description": "Path to the reference image to find",
                    },
                    "timeout_seconds": {
                        "type": "number",
                        "description": "How long to wait for the state (default: 10)",
                        "default": 10,
                    },
                    "similarity_threshold": {
                        "type": "number",
                        "description": "Minimum similarity for a match, 0-1 (default: 0.9)",
                        "default": 0.9,
                    },
                },
                "required": ["state_image_path"],
            },
        ),
        Tool(
            name="wait_for_state",
            description="Wait until a visual state appears on screen or timeout.",
            inputSchema={
                "type": "object",
                "properties": {
                    "state_image_path": {
                        "type": "string",
                        "description": "Path to the reference image to wait for",
                    },
                    "timeout_seconds": {
                        "type": "number",
                        "description": "Maximum time to wait in seconds (default: 30)",
                        "default": 30,
                    },
                },
                "required": ["state_image_path"],
            },
        ),
        Tool(
            name="compare_screenshots",
            description="Compare two screenshots and return difference analysis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "image1_path": {
                        "type": "string",
                        "description": "Path to first image",
                    },
                    "image2_path": {
                        "type": "string",
                        "description": "Path to second image",
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Maximum difference percentage to consider a match (default: 0.05)",
                        "default": 0.05,
                    },
                },
                "required": ["image1_path", "image2_path"],
            },
        ),
        Tool(
            name="is_execution_available",
            description="Check if execution tools are available (qontinui library installed).",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        # Expectations Tools
        Tool(
            name="validate_expectations",
            description="Validate a workflow expectations configuration structure. Checks success criteria, checkpoints, and OCR assertions for correctness.",
            inputSchema={
                "type": "object",
                "properties": {
                    "expectations": {
                        "type": "object",
                        "description": "The expectations configuration JSON to validate",
                    },
                },
                "required": ["expectations"],
            },
        ),
        Tool(
            name="evaluate_expectations",
            description="Evaluate workflow expectations against execution results. Returns pass/fail status for all success criteria and checkpoints.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workflow_id": {
                        "type": "string",
                        "description": "ID of the workflow being evaluated",
                    },
                    "expectations": {
                        "type": "object",
                        "description": "Workflow expectations configuration (global settings, success criteria, checkpoints)",
                    },
                    "execution_stats": {
                        "type": "object",
                        "description": "Execution statistics including total_actions, successful_actions, failed_actions, match_count, states_reached, checkpoints_passed, etc.",
                        "properties": {
                            "total_actions": {"type": "number"},
                            "successful_actions": {"type": "number"},
                            "failed_actions": {"type": "number"},
                            "skipped_actions": {"type": "number"},
                            "match_count": {"type": "number"},
                            "states_reached": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "checkpoints_passed": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "checkpoints_failed": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["workflow_id", "execution_stats"],
            },
        ),
        Tool(
            name="evaluate_checkpoint",
            description="Evaluate a single checkpoint against its definition. Validates OCR assertions against captured text.",
            inputSchema={
                "type": "object",
                "properties": {
                    "checkpoint_name": {
                        "type": "string",
                        "description": "Name of the checkpoint",
                    },
                    "checkpoint_definition": {
                        "type": "object",
                        "description": "Checkpoint definition with ocr_assertions, claude_review, etc.",
                        "properties": {
                            "description": {"type": "string"},
                            "screenshot_required": {"type": "boolean"},
                            "ocr_assertions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {
                                            "type": "string",
                                            "enum": [
                                                "text_present",
                                                "text_absent",
                                                "no_duplicate_matches",
                                                "text_count",
                                                "text_in_region",
                                            ],
                                        },
                                        "text": {"type": "string"},
                                        "case_sensitive": {"type": "boolean"},
                                        "expected_count": {"type": "number"},
                                    },
                                    "required": ["type", "text"],
                                },
                            },
                            "claude_review": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "max_wait_ms": {"type": "number"},
                        },
                    },
                    "screenshot_path": {
                        "type": "string",
                        "description": "Path to captured screenshot (optional)",
                    },
                    "ocr_text": {
                        "type": "string",
                        "description": "OCR text extracted from screenshot (optional)",
                    },
                },
                "required": ["checkpoint_name", "checkpoint_definition"],
            },
        ),
        Tool(
            name="capture_checkpoint",
            description="Capture a checkpoint with screenshot and automatic OCR extraction. This tool captures a screenshot, extracts text using OCR, and evaluates the checkpoint against its definition in one operation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "checkpoint_name": {
                        "type": "string",
                        "description": "Name of the checkpoint",
                    },
                    "checkpoint_definition": {
                        "type": "object",
                        "description": "Checkpoint definition with ocr_assertions, claude_review, etc.",
                        "properties": {
                            "description": {"type": "string"},
                            "screenshot_required": {"type": "boolean"},
                            "ocr_assertions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {
                                            "type": "string",
                                            "enum": [
                                                "text_present",
                                                "text_absent",
                                                "no_duplicate_matches",
                                                "text_count",
                                                "text_in_region",
                                            ],
                                        },
                                        "text": {"type": "string"},
                                        "case_sensitive": {"type": "boolean"},
                                        "expected_count": {"type": "number"},
                                    },
                                    "required": ["type", "text"],
                                },
                            },
                            "claude_review": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "max_wait_ms": {"type": "number"},
                        },
                    },
                    "extract_ocr": {
                        "type": "boolean",
                        "description": "Whether to extract OCR text from screenshot (default: true)",
                        "default": True,
                    },
                },
                "required": ["checkpoint_name", "checkpoint_definition"],
            },
        ),
        # Event Log Search (unified FTS across runner's Postgres event tables)
        Tool(
            name="search_events",
            description=(
                "Full-text search across qontinui-runner's Postgres event tables "
                "(activity_timeline, observations, deferred_questions, error_events). "
                "Returns a ranked list of matching rows with source_table, "
                "record_id, snippet, ts, and score. Requires the 'events' extra "
                "(psycopg) and a reachable RUNNER_DATABASE_URL."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Free-text query. Passed through plainto_tsquery('english', …)."
                        ),
                    },
                    "since_iso": {
                        "type": "string",
                        "description": (
                            "Lower bound on event timestamp as ISO-8601 "
                            "(e.g. '2026-04-10T00:00:00Z'). Defaults to 7 "
                            "days ago (UTC)."
                        ),
                    },
                    "limit": {
                        "type": "number",
                        "description": "Maximum number of rows to return (default 50, capped at 500).",
                        "default": 50,
                    },
                },
                "required": ["query"],
            },
        ),
    ]
    return tools


@server.call_tool()  # type: ignore[untyped-decorator]
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    conn = get_db_connection()
    generator = WorkflowGenerator(conn)

    try:
        result: Any = None

        # Knowledge/Search Tools
        if name == "search_nodes":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 10)
            if not query:
                raise ValueError("Query parameter is required")
            result = search_nodes(conn, query, limit)

        elif name == "search_workflows":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 10)
            if not query:
                raise ValueError("Query parameter is required")
            result = search_workflows(conn, query, limit)

        elif name == "get_nodes_by_category":
            category = arguments.get("category", "")
            if not category:
                raise ValueError("Category parameter is required")
            result = search_nodes_by_category(conn, category)

        elif name == "get_nodes_by_action_type":
            action_type = arguments.get("action_type", "")
            if not action_type:
                raise ValueError("Action type parameter is required")
            result = search_nodes_by_action_type(conn, action_type)

        elif name == "list_categories":
            result = get_all_categories(conn)

        elif name == "get_action_details":
            action_id = arguments.get("action_id", "")
            if not action_id:
                raise ValueError("action_id parameter is required")
            node = get_node(conn, action_id)
            if not node:
                result = {"error": f"Action not found: {action_id}"}
            else:
                result = node

        # Workflow Tools
        elif name == "validate_workflow":
            workflow = arguments.get("workflow")
            if not workflow:
                raise ValueError("workflow parameter is required")
            validation = validate_workflow_structure(workflow)
            result = validation.model_dump()

        elif name == "create_workflow":
            wf_name = arguments.get("name", "")
            description = arguments.get("description", "")
            steps = arguments.get("steps", [])
            if not wf_name or not description or not steps:
                raise ValueError("name, description, and steps parameters are required")
            workflow = generator.create_workflow(wf_name, description, steps)
            validation = validate_workflow_structure(workflow)
            result = {
                "workflow": workflow,
                "validation": validation.model_dump(),
            }

        elif name == "generate_workflow":
            description = arguments.get("description", "")
            if not description:
                raise ValueError("description parameter is required")
            gen_result = generator.generate_from_description(description)
            result = {
                "success": gen_result.success,
                "workflow": gen_result.workflow,
                "error": gen_result.error,
                "suggestions": gen_result.suggestions,
            }

        # Execution Tools
        elif name == "run_automation":
            script = arguments.get("script", "")
            timeout = arguments.get("timeout_seconds", 30)
            capture = arguments.get("capture_screenshot", True)
            expectations = arguments.get("expectations")
            workflow_id = arguments.get("workflow_id")
            if not script:
                raise ValueError("script parameter is required")
            exec_result = run_automation(
                script=script,
                timeout_seconds=timeout,
                capture_screenshot=capture,
                expectations=expectations,
                workflow_id=workflow_id,
            )
            result = {
                "success": exec_result.success,
                "duration_ms": exec_result.duration_ms,
                "errors": exec_result.errors,
                "output": exec_result.output,
                "screenshot_base64": exec_result.screenshot_base64,
            }
            # Include expectations result if present
            if exec_result.expectations_result is not None:
                result["expectations_result"] = {
                    "workflow_id": exec_result.expectations_result.workflow_id,
                    "success": exec_result.expectations_result.success,
                    "criteria_results": exec_result.expectations_result.criteria_results,
                    "checkpoint_results": [
                        cp.model_dump()
                        for cp in (
                            exec_result.expectations_result.checkpoint_results or []
                        )
                    ],
                    "evaluation_summary": exec_result.expectations_result.evaluation_summary,
                    "duration_ms": exec_result.expectations_result.duration_ms,
                }

        elif name == "capture_screenshot":
            screenshot = capture_screen()
            result = {
                "success": screenshot.success,
                "image_base64": screenshot.image_base64,
                "width": screenshot.width,
                "height": screenshot.height,
                "error": screenshot.error,
            }

        elif name == "assert_state_visible":
            state_path = arguments.get("state_image_path", "")
            timeout = arguments.get("timeout_seconds", 10)
            threshold = arguments.get("similarity_threshold", 0.9)
            if not state_path:
                raise ValueError("state_image_path parameter is required")
            assertion = assert_state_visible(state_path, timeout, threshold)
            result = {
                "visible": assertion.visible,
                "confidence": assertion.confidence,
                "location": assertion.location,
                "duration_ms": assertion.duration_ms,
                "error": assertion.error,
            }

        elif name == "wait_for_state":
            state_path = arguments.get("state_image_path", "")
            timeout = arguments.get("timeout_seconds", 30)
            if not state_path:
                raise ValueError("state_image_path parameter is required")
            wait_result = wait_for_state(state_path, timeout)
            result = {
                "found": wait_result.visible,
                "confidence": wait_result.confidence,
                "location": wait_result.location,
                "duration_ms": wait_result.duration_ms,
                "error": wait_result.error,
            }

        elif name == "compare_screenshots":
            image1 = arguments.get("image1_path", "")
            image2 = arguments.get("image2_path", "")
            threshold = arguments.get("threshold", 0.05)
            if not image1 or not image2:
                raise ValueError("image1_path and image2_path parameters are required")
            comparison = compare_screenshots(image1, image2, threshold)
            result = {
                "match": comparison.match,
                "diff_percent": comparison.diff_percent,
                "diff_regions": comparison.diff_regions,
                "diff_image_base64": comparison.diff_image_base64,
                "error": comparison.error,
            }

        elif name == "is_execution_available":
            result = {"available": is_execution_available()}

        # Expectations Tools
        elif name == "validate_expectations":
            expectations = arguments.get("expectations")
            if expectations is None:
                raise ValueError("expectations parameter is required")
            is_valid, errors = validate_expectations_config(expectations)
            result = {
                "valid": is_valid,
                "errors": errors,
            }

        elif name == "evaluate_expectations":
            workflow_id = arguments.get("workflow_id", "")
            if not workflow_id:
                raise ValueError("workflow_id parameter is required")
            expectations = arguments.get("expectations")
            exec_stats = arguments.get("execution_stats", {})

            # Convert array fields to sets for evaluation
            if "states_reached" in exec_stats:
                exec_stats["states_reached"] = set(exec_stats["states_reached"])
            if "checkpoints_passed" in exec_stats:
                exec_stats["checkpoints_passed"] = set(exec_stats["checkpoints_passed"])
            if "checkpoints_failed" in exec_stats:
                exec_stats["checkpoints_failed"] = set(exec_stats["checkpoints_failed"])

            eval_result = evaluate_workflow_expectations(
                workflow_id=workflow_id,
                expectations=expectations,
                execution_stats=exec_stats,
            )
            result = {
                "workflow_id": eval_result.workflow_id,
                "success": eval_result.success,
                "criteria_results": eval_result.criteria_results,
                "checkpoint_results": [
                    cp.model_dump() for cp in (eval_result.checkpoint_results or [])
                ],
                "evaluation_summary": eval_result.evaluation_summary,
                "duration_ms": eval_result.duration_ms,
            }

        elif name == "evaluate_checkpoint":
            checkpoint_name = arguments.get("checkpoint_name", "")
            if not checkpoint_name:
                raise ValueError("checkpoint_name parameter is required")
            checkpoint_def_dict = arguments.get("checkpoint_definition")
            if not checkpoint_def_dict:
                raise ValueError("checkpoint_definition parameter is required")

            # Parse checkpoint definition
            try:
                checkpoint_def = CheckpointDefinition.model_validate(
                    checkpoint_def_dict
                )
            except Exception as e:
                raise ValueError(f"Invalid checkpoint_definition: {e}")

            screenshot_path = arguments.get("screenshot_path")
            ocr_text = arguments.get("ocr_text")

            cp_result = evaluate_checkpoint(
                checkpoint_name=checkpoint_name,
                checkpoint_def=checkpoint_def,
                screenshot_path=screenshot_path,
                ocr_text=ocr_text,
            )
            result = cp_result.model_dump()

        elif name == "capture_checkpoint":
            checkpoint_name = arguments.get("checkpoint_name", "")
            if not checkpoint_name:
                raise ValueError("checkpoint_name parameter is required")
            checkpoint_def_dict = arguments.get("checkpoint_definition")
            if not checkpoint_def_dict:
                raise ValueError("checkpoint_definition parameter is required")

            # Parse checkpoint definition
            try:
                checkpoint_def = CheckpointDefinition.model_validate(
                    checkpoint_def_dict
                )
            except Exception as e:
                raise ValueError(f"Invalid checkpoint_definition: {e}")

            extract_ocr = arguments.get("extract_ocr", True)

            cp_result = capture_checkpoint(
                checkpoint_name=checkpoint_name,
                checkpoint_def=checkpoint_def,
                extract_ocr=extract_ocr,
            )
            result = cp_result.model_dump()

        elif name == "search_events":
            query = arguments.get("query", "")
            if not query:
                raise ValueError("query parameter is required")
            since_iso = arguments.get("since_iso")
            limit = int(arguments.get("limit", 50))
            rows = search_events(query=query, since_iso=since_iso, limit=limit)
            result = {"count": len(rows), "results": rows}

        else:
            raise ValueError(f"Unknown tool: {name}")

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}")
        raise

    finally:
        conn.close()


async def run_server() -> None:
    """Run the MCP server."""
    logger.info("Starting Qontinui MCP Server...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


def main() -> None:
    """Entry point."""
    import asyncio

    asyncio.run(run_server())


if __name__ == "__main__":
    main()
