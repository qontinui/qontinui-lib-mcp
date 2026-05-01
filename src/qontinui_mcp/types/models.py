"""Type definitions for Qontinui nodes, actions, and workflows."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """All available action types in Qontinui."""

    # Basic Actions - Atomic operations
    FIND = "FIND"
    CLICK = "CLICK"
    DOUBLE_CLICK = "DOUBLE_CLICK"
    RIGHT_CLICK = "RIGHT_CLICK"
    MIDDLE_CLICK = "MIDDLE_CLICK"
    DEFINE = "DEFINE"
    TYPE = "TYPE"
    MOVE = "MOVE"
    HOVER = "HOVER"
    VANISH = "VANISH"
    WAIT_VANISH = "WAIT_VANISH"
    HIGHLIGHT = "HIGHLIGHT"
    SCROLL_MOUSE_WHEEL = "SCROLL_MOUSE_WHEEL"
    SCROLL_UP = "SCROLL_UP"
    SCROLL_DOWN = "SCROLL_DOWN"
    MOUSE_DOWN = "MOUSE_DOWN"
    MOUSE_UP = "MOUSE_UP"
    KEY_DOWN = "KEY_DOWN"
    KEY_UP = "KEY_UP"
    CLASSIFY = "CLASSIFY"

    # Composite Actions - Complex operations
    CLICK_UNTIL = "CLICK_UNTIL"
    DRAG = "DRAG"
    RUN_PROCESS = "RUN_PROCESS"


class Region(BaseModel):
    """Region on screen."""

    x: int
    y: int
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class Location(BaseModel):
    """Location (point) on screen."""

    x: int
    y: int


class StateImage(BaseModel):
    """StateImage represents a visual pattern to search for."""

    name: str
    path: str
    similarity: float | None = Field(default=None, ge=0, le=1)
    fixed_region: Region | None = None


class Match(BaseModel):
    """Match result from pattern finding."""

    region: Region
    similarity: float
    image_name: str | None = None


class ObjectCollection(BaseModel):
    """Target object for actions (images, regions, locations)."""

    images: list[StateImage] | None = None
    regions: list[Region] | None = None
    locations: list[Location] | None = None
    strings: list[str] | None = None
    match_objects: list[Match] | None = None


class ActionConfig(BaseModel):
    """Configuration for an action."""

    type: ActionType
    description: str | None = None
    options: dict[str, Any] | None = None
    subsequent_actions: list[ActionConfig] | None = None


class ActionResult(BaseModel):
    """Result of an action execution."""

    success: bool
    matches: list[Match] | None = None
    output_text: str | None = None
    error: str | None = None
    duration_ms: int | None = None


class NodeParameter(BaseModel):
    """Parameter definition for a node."""

    name: str
    type: Literal[
        "string", "number", "boolean", "image", "region", "location", "object"
    ]
    required: bool
    description: str
    default: Any | None = None


class NodeMetadata(BaseModel):
    """Node metadata for search and documentation."""

    id: str
    name: str
    category: str
    description: str
    action_type: ActionType
    parameters: list[NodeParameter]
    examples: list[str] | None = None
    tags: list[str] | None = None


class NodeSearchResult(BaseModel):
    """Search result for nodes."""

    node: NodeMetadata
    score: float
    matched_fields: list[str]


class StepCondition(BaseModel):
    """Condition for step execution."""

    type: Literal["always", "if_success", "if_failure", "if_found", "if_not_found"]
    expression: str | None = None


class RetryConfig(BaseModel):
    """Retry configuration."""

    max_attempts: int = Field(gt=0)
    delay_ms: int = Field(ge=0)
    backoff_multiplier: float | None = Field(default=None, gt=0)


class WorkflowStep(BaseModel):
    """A single step in a workflow."""

    id: str
    name: str
    description: str | None = None
    action: ActionConfig
    condition: StepCondition | None = None
    on_success: str | None = None  # Next step ID
    on_failure: str | None = None  # Next step ID or "exit"
    retry: RetryConfig | None = None
    timeout_ms: int | None = Field(default=None, gt=0)


class WorkflowMetadata(BaseModel):
    """Workflow metadata."""

    created_at: str | None = None
    updated_at: str | None = None
    complexity: Literal["simple", "medium", "complex"] | None = None
    estimated_duration_ms: int | None = None
    category: str | None = None
    prerequisites: list[str] | None = None


class Workflow(BaseModel):
    """A workflow is a named sequence of steps."""

    id: str
    name: str
    description: str
    version: str | None = None
    author: str | None = None
    tags: list[str] | None = None
    steps: list[WorkflowStep]
    variables: dict[str, Any] | None = None
    metadata: WorkflowMetadata | None = None


class WorkflowResult(BaseModel):
    """Result of workflow execution."""

    workflow_id: str
    success: bool
    steps_executed: list[StepResult]
    duration_ms: int
    error: str | None = None
    stopped_at_step: str | None = None


class StepResult(BaseModel):
    """Result of a single step execution."""

    step_id: str
    action_result: ActionResult
    duration_ms: int
    attempts: int


class WorkflowTemplate(BaseModel):
    """Workflow template for search and generation."""

    id: str
    name: str
    description: str
    category: str
    tags: list[str]
    complexity: Literal["simple", "medium", "complex"]
    template: Workflow
    use_cases: list[str]
    customization_points: list[str]


class WorkflowSearchResult(BaseModel):
    """Search result for workflows."""

    workflow: WorkflowTemplate
    score: float
    matched_fields: list[str]


# ============================================================================
# Expectations & Success Criteria Types
# ============================================================================


class SuccessCriteriaType(str, Enum):
    """Types of success criteria for workflow evaluation."""

    ALL_ACTIONS_PASS = "all_actions_pass"
    """All actions must succeed (default behavior)."""

    MIN_MATCHES = "min_matches"
    """At least N matches must be found across all actions."""

    MAX_FAILURES = "max_failures"
    """Allow up to N action failures."""

    CHECKPOINT_PASSED = "checkpoint_passed"
    """Specific named checkpoint action must pass."""

    REQUIRED_STATES = "required_states"
    """Must reach all specified states."""

    CUSTOM = "custom"
    """Custom Python expression evaluated against execution state."""


class SuccessCriterion(BaseModel):
    """A single success criterion definition."""

    criteria_type: SuccessCriteriaType = Field(alias="type")
    description: str | None = None

    # Type-specific parameters
    min_matches: int | None = None
    max_failures: int | None = None
    checkpoint_name: str | None = None
    required_states: list[str] | None = None
    custom_condition: str | None = None


class OCRAssertionType(str, Enum):
    """Types of OCR assertions."""

    TEXT_PRESENT = "text_present"
    TEXT_ABSENT = "text_absent"
    NO_DUPLICATE_MATCHES = "no_duplicate_matches"
    TEXT_COUNT = "text_count"
    TEXT_IN_REGION = "text_in_region"


class OCRAssertion(BaseModel):
    """OCR-based assertion for checkpoint validation."""

    assertion_type: OCRAssertionType = Field(alias="type")
    text: str
    case_sensitive: bool = False
    expected_count: int | None = None
    region: Region | None = None


class CheckpointDefinition(BaseModel):
    """Definition of a checkpoint for validation."""

    description: str | None = None
    screenshot_required: bool = True
    ocr_assertions: list[OCRAssertion] | None = None
    claude_review: list[str] | None = None
    max_wait_ms: int = Field(default=5000, gt=0)
    retry_interval_ms: int = Field(default=500, gt=0)


class GlobalExpectations(BaseModel):
    """Global workflow-level expectations."""

    max_workflow_duration_ms: int | None = None
    max_action_duration_ms: int | None = None
    screenshot_on_failure: bool = True
    fail_fast: bool = False


class WorkflowExpectations(BaseModel):
    """Complete expectations definition for a workflow."""

    global_settings: GlobalExpectations | None = Field(default=None, alias="global")
    success_criteria: list[SuccessCriterion] | None = None
    checkpoints: dict[str, CheckpointDefinition] | None = None


class ActionExpectations(BaseModel):
    """Per-action expectations configuration."""

    is_terminal_on_failure: bool = True
    capture_checkpoint_on_failure: bool = False
    capture_checkpoint_after: bool = False
    checkpoint_name: str | None = None
    max_retries: int | None = None
    retry_delay_ms: int | None = None
    max_duration_ms: int | None = None
    expected_state_after: str | None = None


class CheckpointResult(BaseModel):
    """Result of checkpoint capture and validation."""

    checkpoint_name: str
    timestamp: str
    screenshot_path: str | None = None
    ocr_text: str | None = None
    ocr_assertions_passed: bool = True
    ocr_assertion_results: list[dict[str, Any]] | None = None
    claude_review_results: list[dict[str, Any]] | None = None
    validation_errors: list[str] | None = None


class ExpectationsEvaluationResult(BaseModel):
    """Result of expectations evaluation for a workflow."""

    workflow_id: str
    success: bool
    criteria_results: list[dict[str, Any]]
    checkpoint_results: list[CheckpointResult] | None = None
    evaluation_summary: str
    duration_ms: int
