from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TutorToolName = Literal[
    "explain_current_step",
    "summarize_detected_input",
    "list_blockers",
    "preview_context_bundle_status",
    "compile_context_bundle_after_confirmation",
]

TutorToolStatus = Literal[
    "completed",
    "refused",
    "requires_confirmation",
    "unavailable",
]


class TutorialMessageRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    message: str = Field(min_length=1, max_length=4000)
    context_build_run_id: str | None = None
    current_step: str | None = None
    requested_tool: str | None = None
    detected_input: dict[str, Any] = Field(default_factory=dict)


class TutorialToolConfirmationRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    tool_name: str = Field(min_length=1, max_length=120)
    confirmation_token: str = Field(min_length=1, max_length=240)
    context_build_run_id: str | None = None


class TutorialToolCallResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str
    status: TutorToolStatus
    requires_confirmation: bool = False
    result: dict[str, Any] = Field(default_factory=dict)


class TutorialResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    message: str
    tool_calls: list[TutorialToolCallResponse] = Field(default_factory=list)
