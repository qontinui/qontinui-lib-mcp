"""AI-powered workflow generator.

Generates workflows from natural language descriptions.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from qontinui_mcp.database.search import search_nodes
from qontinui_mcp.utils.validation import validate_workflow_structure

logger = logging.getLogger(__name__)


@dataclass
class WorkflowIntent:
    """Workflow intent parsed from natural language."""

    description: str
    action_keywords: list[str]
    workflow_type: str
    targets: list[str]
    data_inputs: list[dict[str, str]]


@dataclass
class GenerationResult:
    """Workflow generation result."""

    success: bool
    workflow: dict[str, Any] | None = None
    error: str | None = None
    suggestions: list[str] | None = None


class WorkflowGenerator:
    """Workflow generator class."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def generate_from_description(self, description: str) -> GenerationResult:
        """Generate workflow from natural language description."""
        try:
            logger.info(f'Generating workflow from: "{description}"')

            # 1. Parse intent and extract key actions
            intent = self._parse_intent(description)
            logger.debug(f"Parsed intent: {intent}")

            # 2. Match to template if possible
            template = self._match_template(intent)
            if template:
                logger.info(f"Matched template: {template['name']}")
                workflow = self._customize_template(template["template"], intent)
                return GenerationResult(success=True, workflow=workflow)

            # 3. Search for relevant action nodes
            action_nodes = self._find_relevant_actions(intent)
            if not action_nodes:
                return GenerationResult(
                    success=False,
                    error="Could not find relevant actions for the description",
                    suggestions=[
                        "Try using more specific action verbs like 'click', 'type', 'find', 'wait'"
                    ],
                )

            # 4. Generate workflow structure
            workflow = self._build_workflow(intent, action_nodes)

            # 5. Validate the generated workflow
            validation = validate_workflow_structure(workflow)
            if not validation.valid:
                logger.error(f"Generated workflow is invalid: {validation.errors}")
                error_msgs = ", ".join(e.message for e in validation.errors)
                return GenerationResult(
                    success=False,
                    error=f"Generated workflow has validation errors: {error_msgs}",
                )

            logger.info(f"Successfully generated workflow: {workflow['name']}")
            return GenerationResult(success=True, workflow=workflow)

        except Exception as e:
            logger.error(f"Error generating workflow: {e}")
            return GenerationResult(
                success=False,
                error=str(e),
            )

    def _parse_intent(self, description: str) -> WorkflowIntent:
        """Parse natural language description to extract intent."""
        lower = description.lower()

        return WorkflowIntent(
            description=description,
            action_keywords=self._extract_action_keywords(lower),
            workflow_type=self._detect_workflow_type(lower),
            targets=self._extract_targets(lower),
            data_inputs=self._extract_data_inputs(lower),
        )

    def _extract_action_keywords(self, text: str) -> list[str]:
        """Extract action keywords from description."""
        action_words = [
            "click",
            "type",
            "enter",
            "find",
            "search",
            "wait",
            "scroll",
            "drag",
            "hover",
            "move",
            "select",
            "choose",
            "fill",
            "submit",
            "login",
            "navigate",
            "open",
            "close",
            "verify",
            "check",
        ]
        return [word for word in action_words if word in text]

    def _detect_workflow_type(self, text: str) -> str:
        """Detect workflow type from description."""
        if any(kw in text for kw in ["login", "sign in", "authenticate"]):
            return "authentication"
        if any(kw in text for kw in ["form", "fill", "data entry"]):
            return "form-filling"
        if any(kw in text for kw in ["search", "find", "lookup"]):
            return "search"
        if any(kw in text for kw in ["navigate", "browse", "menu"]):
            return "navigation"
        if any(kw in text for kw in ["verify", "check", "validate"]):
            return "validation"
        return "general"

    def _extract_targets(self, text: str) -> list[str]:
        """Extract target elements from description."""
        targets: list[str] = []

        patterns = [
            r"(?:click|find|select)\s+(?:the\s+)?([a-z\s]+?)\s+(?:button|field|input|link|menu|icon)",
            r"(?:type|enter)\s+.*?\s+in(?:to)?\s+(?:the\s+)?([a-z\s]+?)\s+(?:field|input|box)",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                if match.group(1):
                    targets.append(match.group(1).strip())

        return targets

    def _extract_data_inputs(self, text: str) -> list[dict[str, str]]:
        """Extract data inputs from description."""
        inputs: list[dict[str, str]] = []

        # Pattern: type "value" in field
        pattern = r'type\s+"([^"]+)"\s+in(?:to)?\s+(?:the\s+)?([a-z\s]+)'
        for match in re.finditer(pattern, text, re.IGNORECASE):
            inputs.append({"value": match.group(1), "field": match.group(2).strip()})

        return inputs

    def _match_template(self, intent: WorkflowIntent) -> dict[str, Any] | None:
        """Match description to a workflow template."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM workflows WHERE category = ?",
            (intent.workflow_type,),
        )
        row = cursor.fetchone()

        if row:
            return {
                "name": row["name"],
                "template": json.loads(row["template"]),
            }

        return None

    def _customize_template(
        self, template: dict[str, Any], intent: WorkflowIntent
    ) -> dict[str, Any]:
        """Customize a template workflow based on intent."""
        # Clone the template
        workflow = cast(dict[str, Any], json.loads(json.dumps(template)))

        # Update basic info
        workflow["id"] = str(uuid.uuid4())
        workflow["name"] = intent.description[:100]
        workflow["description"] = intent.description

        # Regenerate step IDs
        id_map: dict[str, str] = {}
        for step in workflow["steps"]:
            new_id = str(uuid.uuid4())
            id_map[step["id"]] = new_id
            step["id"] = new_id

        # Update step connections
        for step in workflow["steps"]:
            if step.get("on_success") and step["on_success"] in id_map:
                step["on_success"] = id_map[step["on_success"]]
            if step.get("on_failure") and step["on_failure"] in id_map:
                step["on_failure"] = id_map[step["on_failure"]]

        return workflow

    def _find_relevant_actions(self, intent: WorkflowIntent) -> list[dict[str, Any]]:
        """Find relevant action nodes for the intent."""
        actions: list[dict[str, Any]] = []

        for keyword in intent.action_keywords:
            results = search_nodes(self.conn, keyword, 3)
            for result in results:
                actions.append(
                    {
                        "action": result["node"]["action_type"],
                        "score": result["score"],
                    }
                )

        # Deduplicate and sort by score
        seen: set[str] = set()
        unique_actions: list[dict[str, Any]] = []
        for action in sorted(actions, key=lambda a: a["score"], reverse=True):
            if action["action"] not in seen:
                seen.add(action["action"])
                unique_actions.append(action)

        return unique_actions[:10]

    def _build_workflow(
        self, intent: WorkflowIntent, actions: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Build workflow from intent and relevant actions."""
        workflow_id = str(uuid.uuid4())
        steps: list[dict[str, Any]] = []

        # Create steps for each action keyword
        for i, keyword in enumerate(intent.action_keywords):
            if i >= len(actions):
                break

            step_id = str(uuid.uuid4())
            action = actions[i]["action"]

            action_config: dict[str, Any] = {
                "type": action,
                "description": f"{keyword} action",
                "options": {},
            }

            # Add data inputs if available
            if i < len(intent.data_inputs):
                action_config["options"]["text"] = intent.data_inputs[i]["value"]

            target = intent.targets[i] if i < len(intent.targets) else "target"

            step: dict[str, Any] = {
                "id": step_id,
                "name": f"Step {i + 1}: {keyword}",
                "description": f"{keyword} on {target}",
                "action": action_config,
                "condition": {"type": "always"},
                "timeout_ms": 5000,
                "on_failure": "exit",
            }

            steps.append(step)

        # Connect steps
        for i in range(len(steps) - 1):
            steps[i]["on_success"] = steps[i + 1]["id"]

        # Determine complexity
        if len(steps) <= 3:
            complexity = "simple"
        elif len(steps) <= 7:
            complexity = "medium"
        else:
            complexity = "complex"

        return {
            "id": workflow_id,
            "name": intent.description[:100],
            "description": intent.description,
            "version": "1.0.0",
            "tags": [intent.workflow_type, "generated"],
            "steps": steps,
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "complexity": complexity,
                "category": intent.workflow_type,
            },
        }

    def create_workflow(
        self,
        name: str,
        description: str,
        steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Create a simple workflow with given steps."""
        workflow_id = str(uuid.uuid4())
        workflow_steps: list[dict[str, Any]] = []

        for i, step_def in enumerate(steps):
            step_id = str(uuid.uuid4())

            step: dict[str, Any] = {
                "id": step_id,
                "name": f"Step {i + 1}",
                "description": step_def.get("description"),
                "action": {
                    "type": step_def["action"],
                    "description": step_def.get("description"),
                    "options": step_def.get("options", {}),
                },
                "condition": {"type": "always"},
                "timeout_ms": 5000,
                "on_failure": "exit",
            }

            workflow_steps.append(step)

        # Connect steps
        for i in range(len(workflow_steps) - 1):
            workflow_steps[i]["on_success"] = workflow_steps[i + 1]["id"]

        # Determine complexity
        if len(workflow_steps) <= 3:
            complexity = "simple"
        elif len(workflow_steps) <= 7:
            complexity = "medium"
        else:
            complexity = "complex"

        return {
            "id": workflow_id,
            "name": name,
            "description": description,
            "version": "1.0.0",
            "steps": workflow_steps,
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "complexity": complexity,
            },
        }
