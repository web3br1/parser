from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from context_builder.schemas.tutorial import (
    TutorialMessageRequest,
    TutorialResponse,
    TutorialToolCallResponse,
    TutorialToolConfirmationRequest,
)

READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        "explain_current_step",
        "summarize_detected_input",
        "list_blockers",
        "preview_context_bundle_status",
    }
)
MUTATING_TOOLS: frozenset[str] = frozenset({"compile_context_bundle_after_confirmation"})
ALLOWED_TOOLS: frozenset[str] = READ_ONLY_TOOLS | MUTATING_TOOLS


@dataclass(frozen=True)
class TutorCompileResult:
    status: str
    context_build_run_id: str | None = None
    bundle_hash: str | None = None
    context_version: str | None = None
    output_path: str | None = None
    readiness_status: str | None = None
    readiness_score: int | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "status": self.status,
                "context_build_run_id": self.context_build_run_id,
                "bundle_hash": self.bundle_hash,
                "context_version": self.context_version,
                "output_path": self.output_path,
                "readiness_status": self.readiness_status,
                "readiness_score": self.readiness_score,
                "error": self.error,
            }.items()
            if value is not None
        }


CompileExecutor = Callable[..., TutorCompileResult]


class ContextBuildTutor:
    def __init__(self, compile_executor: CompileExecutor | None = None) -> None:
        self._compile_executor = compile_executor

    def reply_to_message(
        self,
        request: TutorialMessageRequest,
        *,
        workspace_id: str,
        actor_user_id: str,
    ) -> TutorialResponse:
        tool_name = request.requested_tool or self._infer_tool(request.message)
        tool_call = self._run_tool(
            tool_name,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            context_build_run_id=request.context_build_run_id,
            current_step=request.current_step,
            detected_input=request.detected_input,
            confirmation_token=None,
        )
        return TutorialResponse(message=self._message_for(tool_call), tool_calls=[tool_call])

    def confirm_tool(
        self,
        request: TutorialToolConfirmationRequest,
        *,
        workspace_id: str,
        actor_user_id: str,
    ) -> TutorialResponse:
        tool_call = self._run_tool(
            request.tool_name,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            context_build_run_id=request.context_build_run_id,
            current_step=None,
            detected_input={},
            confirmation_token=request.confirmation_token,
        )
        return TutorialResponse(message=self._message_for(tool_call), tool_calls=[tool_call])

    def _run_tool(
        self,
        tool_name: str,
        *,
        workspace_id: str,
        actor_user_id: str,
        context_build_run_id: str | None,
        current_step: str | None,
        detected_input: dict[str, Any],
        confirmation_token: str | None,
    ) -> TutorialToolCallResponse:
        if tool_name not in ALLOWED_TOOLS:
            return TutorialToolCallResponse(
                name=tool_name,
                status="refused",
                result={
                    "code": "tool_not_allowed",
                    "allowed_tools": sorted(ALLOWED_TOOLS),
                },
            )
        if tool_name in MUTATING_TOOLS and not confirmation_token:
            return TutorialToolCallResponse(
                name=tool_name,
                status="requires_confirmation",
                requires_confirmation=True,
                result={
                    "code": "confirmation_required",
                    "confirmation_token_hint": self._confirmation_token(
                        workspace_id,
                        context_build_run_id,
                    ),
                },
            )
        if tool_name in MUTATING_TOOLS and confirmation_token != self._confirmation_token(
            workspace_id,
            context_build_run_id,
        ):
            return TutorialToolCallResponse(
                name=tool_name,
                status="refused",
                result={"code": "invalid_confirmation_token"},
            )
        if tool_name == "compile_context_bundle_after_confirmation":
            return self._compile_after_confirmation(
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                context_build_run_id=context_build_run_id,
            )
        return TutorialToolCallResponse(
            name=tool_name,
            status="completed",
            result=self._read_only_result(
                tool_name,
                current_step=current_step,
                context_build_run_id=context_build_run_id,
                detected_input=detected_input,
            ),
        )

    def _compile_after_confirmation(
        self,
        *,
        workspace_id: str,
        actor_user_id: str,
        context_build_run_id: str | None,
    ) -> TutorialToolCallResponse:
        if self._compile_executor is None:
            return TutorialToolCallResponse(
                name="compile_context_bundle_after_confirmation",
                status="unavailable",
                result={
                    "code": "context_build_compile_unavailable",
                    "message": "Context build compile use case is not wired yet.",
                },
            )
        result = self._compile_executor(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            context_build_run_id=context_build_run_id,
        )
        return TutorialToolCallResponse(
            name="compile_context_bundle_after_confirmation",
            status="completed",
            result=result.as_dict(),
        )

    @staticmethod
    def _read_only_result(
        tool_name: str,
        *,
        current_step: str | None,
        context_build_run_id: str | None,
        detected_input: dict[str, Any],
    ) -> dict[str, Any]:
        if tool_name == "explain_current_step":
            step = current_step or "context_build_start"
            return {
                "step": step,
                "summary": "The tutor can explain the step, but the wizard remains the source of state.",
                "context_build_run_id": context_build_run_id,
            }
        if tool_name == "summarize_detected_input":
            return {
                "summary": "Detected input preview only; backend preflight remains authoritative.",
                "detected_input": detected_input,
            }
        if tool_name == "list_blockers":
            return {
                "blockers": [],
                "note": "No persisted context build blockers were provided to the tutor request.",
            }
        return {
            "status": "not_compiled",
            "context_build_run_id": context_build_run_id,
            "note": "Bundle status preview is read-only in the tutor.",
        }

    @staticmethod
    def _infer_tool(message: str) -> str:
        normalized = message.casefold()
        if "compil" in normalized or "gerar bundle" in normalized:
            return "compile_context_bundle_after_confirmation"
        if "bloque" in normalized or "blocker" in normalized:
            return "list_blockers"
        if "status" in normalized or "bundle" in normalized:
            return "preview_context_bundle_status"
        if "resum" in normalized or "detect" in normalized or "entrada" in normalized:
            return "summarize_detected_input"
        return "explain_current_step"

    @staticmethod
    def _confirmation_token(workspace_id: str, context_build_run_id: str | None) -> str:
        if context_build_run_id:
            return f"confirm-{workspace_id}-{context_build_run_id}-compile_context_bundle_after_confirmation"
        return f"confirm-{workspace_id}-context-build-run-id-compile_context_bundle_after_confirmation"

    @staticmethod
    def _message_for(tool_call: TutorialToolCallResponse) -> str:
        if tool_call.status == "refused":
            return "Essa ferramenta nao esta na allowlist do tutor."
        if tool_call.status == "requires_confirmation":
            return "Preciso de confirmacao explicita antes de compilar o context bundle."
        if tool_call.status == "unavailable":
            return "O compile ainda nao esta disponivel para execucao pelo tutor."
        return "Pronto, executei a ferramenta segura do tutor."
