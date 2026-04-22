"""Expectations evaluation tools for workflow validation.

These tools evaluate success criteria and checkpoint assertions from
workflow configuration, integrating with qontinui's CheckpointService
and SuccessCriteriaEvaluator when available.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..types.models import (
    CheckpointDefinition,
    CheckpointResult,
    ExpectationsEvaluationResult,
    OCRAssertion,
    OCRAssertionType,
    SuccessCriteriaType,
    SuccessCriterion,
    WorkflowExpectations,
)

logger = logging.getLogger(__name__)

# Try to import qontinui components
QONTINUI_AVAILABLE = False
try:
    from qontinui.checkpointing import CheckpointService, CheckpointTrigger  # noqa: F401
    from qontinui.execution.success_criteria import (
        SuccessCriteria as QontinuiSuccessCriteria,  # noqa: F401
    )
    from qontinui.execution.success_criteria import (
        SuccessCriteriaEvaluator,  # noqa: F401
    )
    from qontinui.execution.success_criteria import (
        SuccessCriteriaType as QontinuiCriteriaType,  # noqa: F401
    )

    QONTINUI_AVAILABLE = True
except ImportError:
    logger.warning("qontinui library not available - expectations evaluation limited")


@dataclass
class CriterionEvaluationResult:
    """Result of evaluating a single success criterion."""

    passed: bool
    criterion_type: str
    description: str | None
    evaluation_detail: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OCRAssertionResult:
    """Result of evaluating an OCR assertion."""

    passed: bool
    assertion_type: str
    expected_text: str
    found_text: str | None
    found_count: int
    error: str | None = None


def validate_expectations_config(
    expectations: dict[str, Any] | None,
) -> tuple[bool, list[str]]:
    """Validate expectations configuration structure.

    Args:
        expectations: Raw expectations config from workflow JSON

    Returns:
        Tuple of (is_valid, list of validation errors)
    """
    if expectations is None:
        return True, []

    errors: list[str] = []

    try:
        # Validate global settings
        if "global" in expectations:
            global_config = expectations["global"]
            if not isinstance(global_config, dict):
                errors.append("global must be an object")
            else:
                if "max_workflow_duration_ms" in global_config:
                    if not isinstance(global_config["max_workflow_duration_ms"], int):
                        errors.append("global.max_workflow_duration_ms must be an integer")
                if "max_action_duration_ms" in global_config:
                    if not isinstance(global_config["max_action_duration_ms"], int):
                        errors.append("global.max_action_duration_ms must be an integer")

        # Validate success criteria
        if "success_criteria" in expectations:
            criteria_list = expectations["success_criteria"]
            if not isinstance(criteria_list, list):
                errors.append("success_criteria must be an array")
            else:
                for i, criterion in enumerate(criteria_list):
                    if not isinstance(criterion, dict):
                        errors.append(f"success_criteria[{i}] must be an object")
                        continue
                    if "type" not in criterion:
                        errors.append(f"success_criteria[{i}] missing required 'type' field")
                    else:
                        valid_types = [t.value for t in SuccessCriteriaType]
                        if criterion["type"] not in valid_types:
                            errors.append(
                                f"success_criteria[{i}].type must be one of: {valid_types}"
                            )

                        # Validate type-specific required fields
                        ctype = criterion["type"]
                        if ctype == "min_matches" and "min_matches" not in criterion:
                            errors.append(
                                f"success_criteria[{i}] with type 'min_matches' requires 'min_matches' field"
                            )
                        if ctype == "max_failures" and "max_failures" not in criterion:
                            errors.append(
                                f"success_criteria[{i}] with type 'max_failures' requires 'max_failures' field"
                            )
                        if ctype == "checkpoint_passed" and "checkpoint_name" not in criterion:
                            errors.append(
                                f"success_criteria[{i}] with type 'checkpoint_passed' requires 'checkpoint_name' field"
                            )
                        if ctype == "required_states" and "required_states" not in criterion:
                            errors.append(
                                f"success_criteria[{i}] with type 'required_states' requires 'required_states' field"
                            )
                        if ctype == "custom" and "custom_condition" not in criterion:
                            errors.append(
                                f"success_criteria[{i}] with type 'custom' requires 'custom_condition' field"
                            )

        # Validate checkpoints
        if "checkpoints" in expectations:
            checkpoints = expectations["checkpoints"]
            if not isinstance(checkpoints, dict):
                errors.append("checkpoints must be an object")
            else:
                for name, checkpoint in checkpoints.items():
                    if not isinstance(checkpoint, dict):
                        errors.append(f"checkpoints.{name} must be an object")
                        continue

                    # Validate OCR assertions if present
                    if "ocr_assertions" in checkpoint:
                        assertions = checkpoint["ocr_assertions"]
                        if not isinstance(assertions, list):
                            errors.append(f"checkpoints.{name}.ocr_assertions must be an array")
                        else:
                            for j, assertion in enumerate(assertions):
                                if not isinstance(assertion, dict):
                                    errors.append(
                                        f"checkpoints.{name}.ocr_assertions[{j}] must be an object"
                                    )
                                    continue
                                if "type" not in assertion:
                                    errors.append(
                                        f"checkpoints.{name}.ocr_assertions[{j}] missing 'type'"
                                    )
                                if "text" not in assertion:
                                    errors.append(
                                        f"checkpoints.{name}.ocr_assertions[{j}] missing 'text'"
                                    )

        return len(errors) == 0, errors

    except Exception as e:
        errors.append(f"Validation error: {e}")
        return False, errors


def evaluate_ocr_assertion(
    assertion: OCRAssertion,
    ocr_text: str,
) -> OCRAssertionResult:
    """Evaluate a single OCR assertion against captured text.

    Args:
        assertion: The OCR assertion to evaluate
        ocr_text: The OCR text extracted from screenshot

    Returns:
        OCRAssertionResult with pass/fail status and details
    """
    search_text = assertion.text
    target_text = ocr_text

    if not assertion.case_sensitive:
        search_text = search_text.lower()
        target_text = target_text.lower()

    # Count occurrences
    count = target_text.count(search_text)

    passed = False
    error = None

    try:
        if assertion.assertion_type == OCRAssertionType.TEXT_PRESENT:
            passed = count >= 1
            if not passed:
                error = f"Text '{assertion.text}' not found in OCR output"

        elif assertion.assertion_type == OCRAssertionType.TEXT_ABSENT:
            passed = count == 0
            if not passed:
                error = (
                    f"Text '{assertion.text}' should not be present but was found {count} time(s)"
                )

        elif assertion.assertion_type == OCRAssertionType.NO_DUPLICATE_MATCHES:
            passed = count <= 1
            if not passed:
                error = f"Text '{assertion.text}' found {count} times, expected at most 1"

        elif assertion.assertion_type == OCRAssertionType.TEXT_COUNT:
            expected = assertion.expected_count or 0
            passed = count == expected
            if not passed:
                error = f"Text '{assertion.text}' found {count} times, expected {expected}"

        elif assertion.assertion_type == OCRAssertionType.TEXT_IN_REGION:
            # For region-specific assertions, we'd need region-aware OCR
            # This is a simplified implementation
            passed = count >= 1
            if not passed:
                error = f"Text '{assertion.text}' not found (region assertion simplified)"

    except Exception as e:
        passed = False
        error = f"Assertion evaluation error: {e}"

    return OCRAssertionResult(
        passed=passed,
        assertion_type=assertion.assertion_type.value,
        expected_text=assertion.text,
        found_text=search_text if count > 0 else None,
        found_count=count,
        error=error,
    )


def evaluate_checkpoint(
    checkpoint_name: str,
    checkpoint_def: CheckpointDefinition,
    screenshot_path: str | None = None,
    ocr_text: str | None = None,
) -> CheckpointResult:
    """Evaluate a checkpoint against its definition.

    Args:
        checkpoint_name: Name of the checkpoint
        checkpoint_def: Checkpoint definition with assertions
        screenshot_path: Path to captured screenshot (if any)
        ocr_text: Extracted OCR text (if any)

    Returns:
        CheckpointResult with validation status
    """
    timestamp = datetime.now().isoformat()
    validation_errors: list[str] = []
    ocr_assertions_passed = True
    ocr_assertion_results: list[dict[str, Any]] = []

    # Validate screenshot requirement
    if checkpoint_def.screenshot_required and not screenshot_path:
        validation_errors.append("Screenshot required but not captured")

    # Evaluate OCR assertions if we have OCR text
    if checkpoint_def.ocr_assertions and ocr_text:
        for assertion_config in checkpoint_def.ocr_assertions:
            result = evaluate_ocr_assertion(assertion_config, ocr_text)
            ocr_assertion_results.append(
                {
                    "type": result.assertion_type,
                    "text": result.expected_text,
                    "passed": result.passed,
                    "found_count": result.found_count,
                    "error": result.error,
                }
            )
            if not result.passed:
                ocr_assertions_passed = False
                if result.error:
                    validation_errors.append(result.error)
    elif checkpoint_def.ocr_assertions and not ocr_text:
        ocr_assertions_passed = False
        validation_errors.append("OCR assertions defined but no OCR text available")

    # Claude review instructions would be processed by an external Claude call
    # This just tracks that they exist
    claude_review_results = None
    if checkpoint_def.claude_review:
        claude_review_results = [
            {"instruction": instruction, "status": "pending"}
            for instruction in checkpoint_def.claude_review
        ]

    return CheckpointResult(
        checkpoint_name=checkpoint_name,
        timestamp=timestamp,
        screenshot_path=screenshot_path,
        ocr_text=ocr_text,
        ocr_assertions_passed=ocr_assertions_passed,
        ocr_assertion_results=ocr_assertion_results if ocr_assertion_results else None,
        claude_review_results=claude_review_results,
        validation_errors=validation_errors if validation_errors else None,
    )


def evaluate_success_criteria(
    criteria: SuccessCriterion,
    execution_stats: dict[str, Any],
) -> CriterionEvaluationResult:
    """Evaluate a single success criterion against execution statistics.

    Args:
        criteria: Success criterion to evaluate
        execution_stats: Execution statistics dict with:
            - total_actions: int
            - successful_actions: int
            - failed_actions: int
            - skipped_actions: int
            - match_count: int
            - states_reached: set[str]
            - checkpoints_passed: set[str]
            - checkpoints_failed: set[str]

    Returns:
        CriterionEvaluationResult with pass/fail and explanation
    """
    ctype = criteria.criteria_type
    passed = False
    detail = ""

    try:
        if ctype == SuccessCriteriaType.ALL_ACTIONS_PASS:
            failed = execution_stats.get("failed_actions", 0)
            passed = failed == 0
            if passed:
                successful = execution_stats.get("successful_actions", 0)
                skipped = execution_stats.get("skipped_actions", 0)
                detail = f"All {successful} actions passed ({skipped} skipped)"
            else:
                total = execution_stats.get("total_actions", 0)
                detail = f"{failed} of {total} actions failed"

        elif ctype == SuccessCriteriaType.MIN_MATCHES:
            min_required = criteria.min_matches or 0
            match_count = execution_stats.get("match_count", 0)
            passed = match_count >= min_required
            detail = f"Found {match_count} matches (required: {min_required})"

        elif ctype == SuccessCriteriaType.MAX_FAILURES:
            max_allowed = criteria.max_failures or 0
            failed = execution_stats.get("failed_actions", 0)
            passed = failed <= max_allowed
            detail = f"{failed} failures (allowed: {max_allowed})"

        elif ctype == SuccessCriteriaType.CHECKPOINT_PASSED:
            checkpoint_name = criteria.checkpoint_name or ""
            checkpoints_passed = execution_stats.get("checkpoints_passed", set())
            checkpoints_failed = execution_stats.get("checkpoints_failed", set())
            if checkpoint_name in checkpoints_passed:
                passed = True
                detail = f"Checkpoint '{checkpoint_name}' passed"
            elif checkpoint_name in checkpoints_failed:
                passed = False
                detail = f"Checkpoint '{checkpoint_name}' failed"
            else:
                passed = False
                all_checkpoints = checkpoints_passed | checkpoints_failed
                detail = f"Checkpoint '{checkpoint_name}' not executed (available: {sorted(all_checkpoints)})"

        elif ctype == SuccessCriteriaType.REQUIRED_STATES:
            required = set(criteria.required_states or [])
            reached = execution_stats.get("states_reached", set())
            missing = required - reached
            if not missing:
                passed = True
                detail = f"All required states reached: {sorted(required)}"
            else:
                passed = False
                detail = f"Missing states: {sorted(missing)} (reached: {sorted(reached)})"

        elif ctype == SuccessCriteriaType.CUSTOM:
            # Safe evaluation of custom condition
            condition = criteria.custom_condition or ""
            try:
                import ast

                # Create safe evaluation context
                context = {
                    "total_actions": execution_stats.get("total_actions", 0),
                    "successful_actions": execution_stats.get("successful_actions", 0),
                    "failed_actions": execution_stats.get("failed_actions", 0),
                    "skipped_actions": execution_stats.get("skipped_actions", 0),
                    "match_count": execution_stats.get("match_count", 0),
                    "states_reached": execution_stats.get("states_reached", set()),
                    "checkpoints_passed": execution_stats.get("checkpoints_passed", set()),
                    "checkpoints_failed": execution_stats.get("checkpoints_failed", set()),
                }

                # Parse and evaluate
                parsed = ast.parse(condition, mode="eval")
                result = eval(
                    compile(parsed, "<custom>", "eval"),
                    {"__builtins__": {}},
                    context,
                )
                passed = bool(result)
                detail = f"Custom condition '{condition}' evaluated to {passed}"

            except Exception as e:
                passed = False
                detail = f"Custom condition error: {e}"

    except Exception as e:
        passed = False
        detail = f"Evaluation error: {e}"

    return CriterionEvaluationResult(
        passed=passed,
        criterion_type=ctype.value,
        description=criteria.description,
        evaluation_detail=detail,
    )


def evaluate_workflow_expectations(
    workflow_id: str,
    expectations: WorkflowExpectations | dict[str, Any] | None,
    execution_stats: dict[str, Any],
    checkpoint_results: list[CheckpointResult] | None = None,
) -> ExpectationsEvaluationResult:
    """Evaluate all expectations for a workflow.

    Args:
        workflow_id: ID of the workflow being evaluated
        expectations: Workflow expectations configuration
        execution_stats: Execution statistics
        checkpoint_results: Results from checkpoint evaluations

    Returns:
        ExpectationsEvaluationResult with overall pass/fail
    """
    start_time = time.time()

    # Parse expectations if dict
    if expectations is None:
        # Default: all actions pass
        return ExpectationsEvaluationResult(
            workflow_id=workflow_id,
            success=execution_stats.get("failed_actions", 0) == 0,
            criteria_results=[
                {
                    "type": "all_actions_pass",
                    "passed": execution_stats.get("failed_actions", 0) == 0,
                    "detail": "Default: all actions must pass",
                }
            ],
            checkpoint_results=checkpoint_results,
            evaluation_summary="Default criteria: all actions must pass",
            duration_ms=int((time.time() - start_time) * 1000),
        )

    # Convert dict to model if needed
    if isinstance(expectations, dict):
        try:
            expectations = WorkflowExpectations.model_validate(expectations)
        except Exception as e:
            return ExpectationsEvaluationResult(
                workflow_id=workflow_id,
                success=False,
                criteria_results=[
                    {
                        "type": "validation_error",
                        "passed": False,
                        "detail": f"Invalid expectations config: {e}",
                    }
                ],
                evaluation_summary=f"Configuration error: {e}",
                duration_ms=int((time.time() - start_time) * 1000),
            )

    # Evaluate success criteria
    criteria_results: list[dict[str, Any]] = []
    all_passed = True

    if expectations.success_criteria:
        for criterion in expectations.success_criteria:
            result = evaluate_success_criteria(criterion, execution_stats)
            criteria_results.append(
                {
                    "type": result.criterion_type,
                    "passed": result.passed,
                    "description": result.description,
                    "detail": result.evaluation_detail,
                }
            )
            if not result.passed:
                all_passed = False
    else:
        # Default to all_actions_pass if no criteria specified
        failed = execution_stats.get("failed_actions", 0)
        default_passed = failed == 0
        criteria_results.append(
            {
                "type": "all_actions_pass",
                "passed": default_passed,
                "description": "Default criteria",
                "detail": f"All actions must pass ({failed} failures)",
            }
        )
        if not default_passed:
            all_passed = False

    # Check checkpoint validations
    if checkpoint_results:
        for cp_result in checkpoint_results:
            if cp_result.validation_errors:
                all_passed = False

    # Generate summary
    passed_count = sum(1 for r in criteria_results if r["passed"])
    total_count = len(criteria_results)
    summary = f"{passed_count}/{total_count} criteria passed"

    if checkpoint_results:
        cp_passed = sum(1 for cp in checkpoint_results if not cp.validation_errors)
        summary += f", {cp_passed}/{len(checkpoint_results)} checkpoints passed"

    duration_ms = int((time.time() - start_time) * 1000)

    return ExpectationsEvaluationResult(
        workflow_id=workflow_id,
        success=all_passed,
        criteria_results=criteria_results,
        checkpoint_results=checkpoint_results,
        evaluation_summary=summary,
        duration_ms=duration_ms,
    )
