"""Validation utilities using Pydantic."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from qontinui_mcp.types.models import ActionConfig, ActionType, Workflow


class ValidationError(BaseModel):
    """Validation error details."""

    field: str
    message: str
    code: str


class WorkflowValidationResult(BaseModel):
    """Workflow validation result."""

    valid: bool
    errors: list[ValidationError]
    warnings: list[ValidationError] | None = None


def validate_action_config(config: dict[str, Any]) -> ActionConfig:
    """Validate an action configuration."""
    return ActionConfig.model_validate(config)


def validate_workflow(workflow: dict[str, Any]) -> Workflow:
    """Validate a workflow."""
    return Workflow.model_validate(workflow)


def validate_workflow_structure(workflow: dict[str, Any]) -> WorkflowValidationResult:
    """Comprehensive workflow validation with cycle detection and connection checks."""
    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []

    # 1. Basic schema validation
    try:
        wf = Workflow.model_validate(workflow)
    except PydanticValidationError as e:
        errors.append(
            ValidationError(
                field="schema",
                message=str(e),
                code="INVALID_SCHEMA",
            )
        )
        return WorkflowValidationResult(valid=False, errors=errors)

    # 2. Check for empty steps
    if len(wf.steps) == 0:
        errors.append(
            ValidationError(
                field="steps",
                message="Workflow must have at least one step",
                code="EMPTY_WORKFLOW",
            )
        )
        return WorkflowValidationResult(valid=False, errors=errors)

    # 3. Validate step IDs are unique
    step_ids: set[str] = set()
    for step in wf.steps:
        if step.id in step_ids:
            errors.append(
                ValidationError(
                    field=f"steps.{step.id}",
                    message=f"Duplicate step ID: {step.id}",
                    code="DUPLICATE_STEP_ID",
                )
            )
        step_ids.add(step.id)

    # 4. Validate step connections (on_success, on_failure)
    for step in wf.steps:
        if step.on_success and step.on_success not in step_ids:
            errors.append(
                ValidationError(
                    field=f"steps.{step.id}.on_success",
                    message=f"on_success references non-existent step: {step.on_success}",
                    code="INVALID_CONNECTION",
                )
            )
        if (
            step.on_failure
            and step.on_failure != "exit"
            and step.on_failure not in step_ids
        ):
            errors.append(
                ValidationError(
                    field=f"steps.{step.id}.on_failure",
                    message=f"on_failure references non-existent step: {step.on_failure}",
                    code="INVALID_CONNECTION",
                )
            )

    # 5. Detect cycles in workflow graph
    cycles = _detect_cycles(wf.steps)
    for cycle in cycles:
        errors.append(
            ValidationError(
                field="workflow",
                message=f"Cycle detected: {' -> '.join(cycle)}",
                code="CYCLE_DETECTED",
            )
        )

    # 6. Check for unreachable steps
    reachable_steps = _find_reachable_steps(wf.steps)
    for step in wf.steps:
        if step.id not in reachable_steps:
            warnings.append(
                ValidationError(
                    field=f"steps.{step.id}",
                    message=f"Step is unreachable: {step.id}",
                    code="UNREACHABLE_STEP",
                )
            )

    # 7. Validate action types exist
    valid_action_types = {at.value for at in ActionType}
    for step in wf.steps:
        action_type = step.action.type
        type_value = action_type.value if hasattr(action_type, "value") else action_type
        if type_value not in valid_action_types:
            errors.append(
                ValidationError(
                    field=f"steps.{step.id}.action.type",
                    message=f"Invalid action type: {type_value}",
                    code="INVALID_ACTION_TYPE",
                )
            )

    return WorkflowValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings if warnings else None,
    )


def _detect_cycles(steps: list[Any]) -> list[list[str]]:
    """Detect cycles in workflow graph using DFS."""
    cycles: list[list[str]] = []
    visited: set[str] = set()
    recursion_stack: set[str] = set()
    current_path: list[str] = []

    step_map = {step.id: step for step in steps}

    def dfs(step_id: str) -> None:
        if step_id in recursion_stack:
            # Found a cycle
            cycle_start = current_path.index(step_id) if step_id in current_path else -1
            if cycle_start != -1:
                cycles.append(current_path[cycle_start:] + [step_id])
            return

        if step_id in visited:
            return

        visited.add(step_id)
        recursion_stack.add(step_id)
        current_path.append(step_id)

        step = step_map.get(step_id)
        if step:
            if step.on_success:
                dfs(step.on_success)
            if step.on_failure and step.on_failure != "exit":
                dfs(step.on_failure)

        current_path.pop()
        recursion_stack.remove(step_id)

    # Start DFS from first step
    if steps:
        dfs(steps[0].id)

    return cycles


def _find_reachable_steps(steps: list[Any]) -> set[str]:
    """Find all reachable steps from the first step."""
    reachable: set[str] = set()

    if not steps:
        return reachable

    step_map = {step.id: step for step in steps}
    queue = [steps[0].id]

    while queue:
        step_id = queue.pop(0)

        if step_id in reachable:
            continue

        reachable.add(step_id)

        step = step_map.get(step_id)
        if step:
            if step.on_success and step.on_success not in reachable:
                queue.append(step.on_success)
            if (
                step.on_failure
                and step.on_failure != "exit"
                and step.on_failure not in reachable
            ):
                queue.append(step.on_failure)

    return reachable
