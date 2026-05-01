"""Execution tools for running Qontinui automations.

These tools interface directly with the qontinui library to execute
automation scripts, capture screenshots, and verify states.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..types.models import (
    CheckpointDefinition,
    CheckpointResult,
    ExpectationsEvaluationResult,
    WorkflowExpectations,
)
from .expectations import evaluate_workflow_expectations

logger = logging.getLogger(__name__)

# Try to import qontinui - if not available, execution tools will be disabled
QONTINUI_AVAILABLE = False
try:
    # Import will be added when qontinui package is available
    # from qontinui import Automation, Screen, State
    QONTINUI_AVAILABLE = False  # Set to True when qontinui is importable
except ImportError:
    logger.warning("qontinui library not available - execution tools disabled")

# Import OCR capabilities
try:
    from .ocr import extract_ocr_text, is_ocr_available
except ImportError:
    logger.warning("OCR module not available")

    def is_ocr_available() -> bool:
        return False

    def extract_ocr_text(image_source: str) -> str | None:
        return None


@dataclass
class ExecutionResult:
    """Result of automation execution."""

    success: bool
    duration_ms: int
    errors: list[str] = field(default_factory=list)
    output: dict[str, Any] | None = None
    screenshot_base64: str | None = None
    expectations_result: ExpectationsEvaluationResult | None = None


@dataclass
class ScreenshotResult:
    """Result of screenshot capture."""

    success: bool
    image_base64: str | None = None
    width: int | None = None
    height: int | None = None
    error: str | None = None


@dataclass
class StateAssertionResult:
    """Result of state assertion."""

    visible: bool
    confidence: float | None = None
    location: dict[str, int] | None = None
    duration_ms: int = 0
    error: str | None = None


@dataclass
class ScreenshotComparisonResult:
    """Result of screenshot comparison."""

    match: bool
    diff_percent: float
    diff_regions: list[dict[str, int]] = field(default_factory=list)
    diff_image_base64: str | None = None
    error: str | None = None


def is_execution_available() -> bool:
    """Check if execution tools are available."""
    return QONTINUI_AVAILABLE


def run_automation(
    script: str,
    timeout_seconds: int = 30,
    capture_screenshot: bool = True,
    expectations: WorkflowExpectations | dict[str, Any] | None = None,
    workflow_id: str | None = None,
) -> ExecutionResult:
    """Execute a Qontinui automation script.

    Args:
        script: The automation script in DSL format or JSON workflow
        timeout_seconds: Maximum execution time
        capture_screenshot: Whether to capture final screenshot
        expectations: Optional workflow expectations to evaluate after execution
        workflow_id: Optional workflow ID for expectations evaluation

    Returns:
        ExecutionResult with success status, duration, optional screenshot, and expectations result
    """
    if not QONTINUI_AVAILABLE:
        return ExecutionResult(
            success=False,
            duration_ms=0,
            errors=["qontinui library not available"],
        )

    start_time = time.time()

    try:
        # TODO: Implement actual execution when qontinui is available
        # from qontinui import Automation
        # auto = Automation.from_dsl(script)
        # result = auto.execute(timeout=timeout_seconds)

        # Placeholder implementation
        duration_ms = int((time.time() - start_time) * 1000)

        # Placeholder execution statistics
        # In real implementation, these would come from the actual execution
        execution_stats = {
            "total_actions": 0,
            "successful_actions": 0,
            "failed_actions": 0,
            "skipped_actions": 0,
            "match_count": 0,
            "states_reached": set(),
            "checkpoints_passed": set(),
            "checkpoints_failed": set(),
        }

        # Evaluate expectations if provided
        expectations_result = None
        if expectations is not None:
            wf_id = workflow_id or "unknown_workflow"
            expectations_result = evaluate_workflow_expectations(
                workflow_id=wf_id,
                expectations=expectations,
                execution_stats=execution_stats,
            )

        return ExecutionResult(
            success=True,
            duration_ms=duration_ms,
            output={"message": "Execution placeholder - qontinui integration pending"},
            expectations_result=expectations_result,
        )

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Automation execution failed: {e}")
        return ExecutionResult(
            success=False,
            duration_ms=duration_ms,
            errors=[str(e)],
        )


def capture_screen() -> ScreenshotResult:
    """Capture the current screen.

    Returns:
        ScreenshotResult with base64-encoded image
    """
    if not QONTINUI_AVAILABLE:
        return ScreenshotResult(
            success=False,
            error="qontinui library not available",
        )

    try:
        # TODO: Implement actual screenshot when qontinui is available
        # from qontinui import Screen
        # screenshot = Screen.capture()
        # return ScreenshotResult(
        #     success=True,
        #     image_base64=screenshot.to_base64(),
        #     width=screenshot.width,
        #     height=screenshot.height,
        # )

        return ScreenshotResult(
            success=False,
            error="Screenshot capture not yet implemented",
        )

    except Exception as e:
        logger.error(f"Screenshot capture failed: {e}")
        return ScreenshotResult(
            success=False,
            error=str(e),
        )


def assert_state_visible(
    state_image_path: str,
    timeout_seconds: int = 10,
    similarity_threshold: float = 0.9,
) -> StateAssertionResult:
    """Assert that a state/element is visible on screen.

    Args:
        state_image_path: Path to the reference image
        timeout_seconds: How long to wait for the state
        similarity_threshold: Minimum similarity for a match

    Returns:
        StateAssertionResult with visibility status and match details
    """
    if not QONTINUI_AVAILABLE:
        return StateAssertionResult(
            visible=False,
            error="qontinui library not available",
        )

    start_time = time.time()

    try:
        # Verify the image path exists
        if not Path(state_image_path).exists():
            return StateAssertionResult(
                visible=False,
                error=f"State image not found: {state_image_path}",
                duration_ms=int((time.time() - start_time) * 1000),
            )

        # TODO: Implement actual state detection when qontinui is available
        # from qontinui import State
        # state = State.from_image(state_image_path, similarity=similarity_threshold)
        # found = state.wait_until_visible(timeout=timeout_seconds)
        # return StateAssertionResult(
        #     visible=found,
        #     confidence=state.last_match_confidence,
        #     location=state.last_match_location,
        #     duration_ms=int((time.time() - start_time) * 1000),
        # )

        return StateAssertionResult(
            visible=False,
            error="State assertion not yet implemented",
            duration_ms=int((time.time() - start_time) * 1000),
        )

    except Exception as e:
        logger.error(f"State assertion failed: {e}")
        return StateAssertionResult(
            visible=False,
            error=str(e),
            duration_ms=int((time.time() - start_time) * 1000),
        )


def wait_for_state(
    state_image_path: str,
    timeout_seconds: int = 30,
    poll_interval_ms: int = 500,
) -> StateAssertionResult:
    """Wait until a state appears on screen.

    Args:
        state_image_path: Path to the reference image
        timeout_seconds: Maximum time to wait
        poll_interval_ms: How often to check

    Returns:
        StateAssertionResult with whether state was found
    """
    return assert_state_visible(
        state_image_path=state_image_path,
        timeout_seconds=timeout_seconds,
    )


def compare_screenshots(
    image1_path: str,
    image2_path: str,
    threshold: float = 0.05,
) -> ScreenshotComparisonResult:
    """Compare two screenshots and return difference analysis.

    Args:
        image1_path: Path to first image
        image2_path: Path to second image
        threshold: Maximum difference percentage to consider a match

    Returns:
        ScreenshotComparisonResult with diff details
    """
    try:
        # Verify both images exist
        if not Path(image1_path).exists():
            return ScreenshotComparisonResult(
                match=False,
                diff_percent=100.0,
                error=f"Image not found: {image1_path}",
            )

        if not Path(image2_path).exists():
            return ScreenshotComparisonResult(
                match=False,
                diff_percent=100.0,
                error=f"Image not found: {image2_path}",
            )

        # TODO: Implement actual comparison
        # This could use PIL, OpenCV, or qontinui's comparison utilities

        return ScreenshotComparisonResult(
            match=False,
            diff_percent=0.0,
            error="Screenshot comparison not yet implemented",
        )

    except Exception as e:
        logger.error(f"Screenshot comparison failed: {e}")
        return ScreenshotComparisonResult(
            match=False,
            diff_percent=100.0,
            error=str(e),
        )


def click_at(x: int, y: int) -> ExecutionResult:
    """Click at a specific screen location.

    Args:
        x: X coordinate
        y: Y coordinate

    Returns:
        ExecutionResult with success status
    """
    if not QONTINUI_AVAILABLE:
        return ExecutionResult(
            success=False,
            duration_ms=0,
            errors=["qontinui library not available"],
        )

    start_time = time.time()

    try:
        # TODO: Implement when qontinui is available
        # from qontinui import Mouse
        # Mouse.click(x, y)

        return ExecutionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            errors=["Click not yet implemented"],
        )

    except Exception as e:
        return ExecutionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            errors=[str(e)],
        )


def type_text(text: str) -> ExecutionResult:
    """Type text using keyboard simulation.

    Args:
        text: Text to type

    Returns:
        ExecutionResult with success status
    """
    if not QONTINUI_AVAILABLE:
        return ExecutionResult(
            success=False,
            duration_ms=0,
            errors=["qontinui library not available"],
        )

    start_time = time.time()

    try:
        # TODO: Implement when qontinui is available
        # from qontinui import Keyboard
        # Keyboard.type(text)

        return ExecutionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            errors=["Type not yet implemented"],
        )

    except Exception as e:
        return ExecutionResult(
            success=False,
            duration_ms=int((time.time() - start_time) * 1000),
            errors=[str(e)],
        )


def capture_checkpoint(
    checkpoint_name: str,
    checkpoint_def: CheckpointDefinition,
    extract_ocr: bool = True,
) -> CheckpointResult:
    """Capture a checkpoint with screenshot and optional OCR extraction.

    This function captures a screenshot and automatically extracts OCR text
    if the checkpoint definition includes OCR assertions. The checkpoint is
    then evaluated against its definition.

    Args:
        checkpoint_name: Name of the checkpoint
        checkpoint_def: Checkpoint definition with assertions
        extract_ocr: Whether to extract OCR text from screenshot (default: True)

    Returns:
        CheckpointResult with validation status and OCR results

    Example:
        >>> from qontinui_mcp.types.models import CheckpointDefinition, OCRAssertion, OCRAssertionType
        >>> checkpoint = CheckpointDefinition(
        ...     description="Login page checkpoint",
        ...     screenshot_required=True,
        ...     ocr_assertions=[
        ...         OCRAssertion(
        ...             assertion_type=OCRAssertionType.TEXT_PRESENT,
        ...             text="Login",
        ...             case_sensitive=False
        ...         )
        ...     ]
        ... )
        >>> result = capture_checkpoint("login_page", checkpoint)
        >>> print(f"Checkpoint passed: {result.ocr_assertions_passed}")
    """
    from datetime import datetime

    from .expectations import evaluate_checkpoint

    timestamp = datetime.now().isoformat()
    screenshot_path: str | None = None
    ocr_text: str | None = None
    validation_errors: list[str] = []

    try:
        # Capture screenshot if required
        if checkpoint_def.screenshot_required:
            screenshot_result = capture_screen()

            if screenshot_result.success and screenshot_result.image_base64:
                # Save screenshot to temp file or use base64 directly
                screenshot_path = f"checkpoint_{checkpoint_name}_{timestamp}.png"
                logger.info(f"Screenshot captured for checkpoint '{checkpoint_name}'")

                # Extract OCR text if requested and OCR assertions are defined
                if extract_ocr and checkpoint_def.ocr_assertions and is_ocr_available():
                    logger.info(
                        f"Extracting OCR text for checkpoint '{checkpoint_name}'"
                    )
                    ocr_text = extract_ocr_text(screenshot_result.image_base64)

                    if ocr_text is None:
                        validation_errors.append("OCR extraction failed")
                        logger.warning(
                            f"OCR extraction failed for checkpoint '{checkpoint_name}'"
                        )
                    else:
                        logger.info(
                            f"Extracted {len(ocr_text)} characters from checkpoint '{checkpoint_name}'"
                        )
                elif extract_ocr and checkpoint_def.ocr_assertions:
                    validation_errors.append("OCR not available for assertions")
                    logger.warning("OCR assertions defined but OCR not available")

            else:
                validation_errors.append(
                    f"Screenshot capture failed: {screenshot_result.error}"
                )
                logger.error(
                    f"Screenshot capture failed for checkpoint '{checkpoint_name}': {screenshot_result.error}"
                )

    except Exception as e:
        validation_errors.append(f"Checkpoint capture error: {e}")
        logger.error(f"Error capturing checkpoint '{checkpoint_name}': {e}")

    # Evaluate checkpoint with captured data
    result = evaluate_checkpoint(
        checkpoint_name=checkpoint_name,
        checkpoint_def=checkpoint_def,
        screenshot_path=screenshot_path,
        ocr_text=ocr_text,
    )

    # Add any capture errors to validation errors
    if validation_errors:
        if result.validation_errors:
            result.validation_errors.extend(validation_errors)
        else:
            result.validation_errors = validation_errors

    return result
