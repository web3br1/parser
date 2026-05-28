"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { Bot, CheckCircle2, Loader2, Send, X } from "lucide-react";
import {
  AlertMessage,
  Panel,
  PanelHeader,
  StatusBadge
} from "@/components/console-primitives";
import {
  apiMessage,
  confirmTutorialTool,
  sendTutorialMessage,
  type TutorCompileToolResult,
  type TutorRequiresConfirmationResult,
  type TutorialMessageRequest,
  type TutorialToolCall
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Type guards — result is Record<string, unknown> at the boundary
// ---------------------------------------------------------------------------

function isRequiresConfirmationResult(
  result: Record<string, unknown>
): result is TutorRequiresConfirmationResult {
  return (
    result["code"] === "confirmation_required" &&
    typeof result["confirmation_token_hint"] === "string"
  );
}

function isCompileToolResult(
  result: Record<string, unknown>
): result is TutorCompileToolResult {
  return (
    result["status"] === "compiled" ||
    result["status"] === "failed"
  );
}

// ---------------------------------------------------------------------------
// Internal state types
// ---------------------------------------------------------------------------

type UserEntry = { kind: "user"; text: string };
type TutorEntry = { kind: "tutor"; text: string; toolCall: TutorialToolCall };
type ChatEntry = UserEntry | TutorEntry;

/** Token is always read from confirmation_token_hint — never hardcoded. */
type PendingConfirmation = {
  toolName: string;
  token: string;
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export type TutorPanelProps = {
  workspaceId: string;
  token: string;
  contextBuildRunId: string | null;
  disabled?: boolean;
  onCompileResult?: (result: TutorCompileToolResult) => void;
};

/**
 * Imperative handle exposed via forwardRef.
 * The wizard calls sendMessage to trigger a pre-filled tutor exchange
 * (e.g. contextual message after preflight, or CTA "Compilar via Tutor").
 */
export type TutorPanelHandle = {
  sendMessage: (text: string) => void;
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900">
        {text}
      </div>
    </div>
  );
}

function TutorBubble({
  text,
  toolCall,
  isMostRecent,
  pending,
  loading,
  onConfirm,
  onCancel
}: {
  text: string;
  toolCall: TutorialToolCall;
  isMostRecent: boolean;
  pending: PendingConfirmation | null;
  loading: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const showConfirmBar =
    isMostRecent &&
    toolCall.status === "requires_confirmation" &&
    pending !== null;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start gap-2">
        <div
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded border border-slate-200 bg-white"
          aria-hidden="true"
        >
          <Bot className="h-3.5 w-3.5 text-slate-500" />
        </div>
        <p className="text-sm text-slate-700">{text}</p>
      </div>

      <ToolCallCard toolCall={toolCall} />

      {showConfirmBar && (
        <ConfirmationBar loading={loading} onConfirm={onConfirm} onCancel={onCancel} />
      )}
    </div>
  );
}

function ToolCallCard({ toolCall }: { toolCall: TutorialToolCall }) {
  const { name, status, result } = toolCall;
  const isCompileTool = name === "compile_context_bundle_after_confirmation";

  return (
    <div className="ml-8 rounded border border-slate-200 bg-slate-50 p-3 text-xs">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="font-mono text-slate-500">{name}</span>
        <StatusBadge value={status} />
      </div>

      {isCompileTool && isCompileToolResult(result) && (
        <CompileResultDetails result={result} />
      )}

      {status === "refused" && typeof result["code"] === "string" && (
        <p className="text-red-700">
          Recusado: {result["code"]}
          {Array.isArray(result["allowed_tools"]) && (
            <span className="ml-1 text-slate-500">
              (permitidas: {(result["allowed_tools"] as string[]).join(", ")})
            </span>
          )}
        </p>
      )}
    </div>
  );
}

function CompileResultDetails({ result }: { result: TutorCompileToolResult }) {
  return (
    <dl className="space-y-1">
      {result.bundle_hash && (
        <CompileField label="bundle_hash" value={result.bundle_hash} />
      )}
      {result.context_version && (
        <CompileField label="context_version" value={result.context_version} />
      )}
      {result.readiness_status && (
        <CompileField label="readiness_status" value={result.readiness_status} />
      )}
      {result.readiness_score !== undefined && (
        <CompileField label="readiness_score" value={String(result.readiness_score)} />
      )}
      {result.output_path && (
        <CompileField label="output_path" value={result.output_path} />
      )}
      {result.error && (
        <CompileField label="error" value={result.error} tone="error" />
      )}
    </dl>
  );
}

function CompileField({
  label,
  value,
  tone
}: {
  label: string;
  value: string;
  tone?: "error";
}) {
  return (
    <div>
      <dt className="inline text-slate-500">{label}: </dt>
      <dd
        className={`inline break-all font-medium ${
          tone === "error" ? "text-red-700" : "text-slate-800"
        }`}
      >
        {value}
      </dd>
    </div>
  );
}

function ConfirmationBar({
  loading,
  onConfirm,
  onCancel
}: {
  loading: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="ml-8 flex items-center gap-2">
      <button
        type="button"
        onClick={onConfirm}
        disabled={loading}
        className="inline-flex h-7 items-center gap-1.5 rounded bg-slate-950 px-3 text-xs font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? (
          <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
        ) : (
          <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
        )}
        Confirmar
      </button>
      <button
        type="button"
        onClick={onCancel}
        disabled={loading}
        className="inline-flex h-7 items-center gap-1.5 rounded border border-slate-200 bg-white px-3 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <X className="h-3 w-3" aria-hidden="true" />
        Cancelar
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export const TutorPanel = forwardRef<TutorPanelHandle, TutorPanelProps>(
function TutorPanel({
  workspaceId,
  token,
  contextBuildRunId,
  disabled = false,
  onCompileResult
}: TutorPanelProps, ref) {
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState<PendingConfirmation | null>(null);
  const [error, setError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);

  // Scroll after render, not inside async handlers — avoids reading stale DOM.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries.length]);

  // Core send logic, shared by handleSend (user typed) and sendMessage (wizard CTA).
  async function executeSend(text: string) {
    if (!text || loading || disabled) return;

    setError(null);
    setEntries((prev) => [...prev, { kind: "user", text }]);
    setLoading(true);

    const payload: TutorialMessageRequest = {
      message: text,
      context_build_run_id: contextBuildRunId
    };

    try {
      const response = await sendTutorialMessage(workspaceId, token, payload);
      const toolCall = response.tool_calls[0];
      if (!toolCall) return;

      setEntries((prev) => [
        ...prev,
        { kind: "tutor", text: response.message, toolCall }
      ]);

      // If the tool requires confirmation, capture the token from the response —
      // never hardcode it. The token is workspace+run scoped.
      if (
        toolCall.status === "requires_confirmation" &&
        isRequiresConfirmationResult(toolCall.result)
      ) {
        setPending({
          toolName: toolCall.name,
          token: toolCall.result.confirmation_token_hint
        });
      }
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setLoading(false);
    }
  }

  // Called when the user submits the textarea.
  async function handleSend() {
    const text = input.trim();
    if (!text) return;
    setInput("");
    await executeSend(text);
  }

  // Exposed to parent via ref — lets the wizard trigger messages programmatically.
  useImperativeHandle(ref, () => ({
    sendMessage(text: string) {
      void executeSend(text.trim());
    }
  }));

  async function handleConfirm() {
    if (!pending || loading) return;

    // Capture before async gap — setPending(null) below clears it.
    const captured = pending;
    setLoading(true);
    setError(null);

    try {
      const response = await confirmTutorialTool(workspaceId, token, {
        tool_name: captured.toolName,
        confirmation_token: captured.token,
        context_build_run_id: contextBuildRunId
      });

      setPending(null);
      const toolCall = response.tool_calls[0];
      if (!toolCall) return;

      setEntries((prev) => [
        ...prev,
        { kind: "tutor", text: response.message, toolCall }
      ]);

      // Fire the compile result callback only when the compile actually succeeded.
      if (
        toolCall.name === "compile_context_bundle_after_confirmation" &&
        toolCall.status === "completed" &&
        isCompileToolResult(toolCall.result) &&
        toolCall.result.status === "compiled"
      ) {
        onCompileResult?.(toolCall.result);
      }
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setLoading(false);
    }
  }

  function handleCancel() {
    // Capture before clearing.
    const captured = pending;
    setPending(null);
    setEntries((prev) => [
      ...prev,
      {
        kind: "tutor",
        text: "Compilação cancelada.",
        toolCall: {
          name: captured?.toolName ?? "compile_context_bundle_after_confirmation",
          status: "refused" as const,
          requires_confirmation: false,
          result: { code: "cancelled_by_user" }
        }
      }
    ]);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  // Input is locked while loading or while a confirmation is pending.
  const inputLocked = disabled || loading || !!pending;

  return (
    <Panel className="flex flex-col overflow-hidden">
      <PanelHeader>Tutor</PanelHeader>

      {/* Message list — flex-1 + overflow-y-auto to scroll within the panel */}
      <div className="flex-1 overflow-y-auto p-4">
        {entries.length === 0 && (
          <p className="text-center text-sm text-slate-400">
            Envie uma mensagem para o tutor explicar o passo atual ou guiar a compilação.
          </p>
        )}

        <div className="space-y-4">
          {entries.map((entry, index) => {
            if (entry.kind === "user") {
              return <UserBubble key={index} text={entry.text} />;
            }
            return (
              <TutorBubble
                key={index}
                text={entry.text}
                toolCall={entry.toolCall}
                isMostRecent={index === entries.length - 1}
                pending={pending}
                loading={loading}
                onConfirm={() => void handleConfirm()}
                onCancel={handleCancel}
              />
            );
          })}
        </div>

        <div ref={bottomRef} aria-hidden="true" />
      </div>

      {/* Inline error — below messages, above input */}
      {error && (
        <div className="px-4 pb-0">
          <AlertMessage tone="error">{error}</AlertMessage>
        </div>
      )}

      {/* Input area */}
      <div className="border-t border-slate-200 p-3">
        <div className="flex items-end gap-2">
          <textarea
            aria-label="Mensagem para o tutor"
            className="min-h-[60px] flex-1 resize-none rounded border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-slate-400 disabled:bg-slate-50 disabled:text-slate-400"
            placeholder={
              pending
                ? "Confirme ou cancele a ação acima antes de continuar."
                : "Pergunte ao tutor sobre o passo atual..."
            }
            value={input}
            disabled={inputLocked}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
          />
          <button
            type="button"
            aria-label="Enviar mensagem"
            onClick={() => void handleSend()}
            disabled={inputLocked || !input.trim()}
            className="inline-flex h-9 items-center gap-1.5 rounded bg-slate-950 px-3 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Send className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        </div>
      </div>
    </Panel>
  );
});
