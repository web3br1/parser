"use client";

import { FormEvent, useMemo, useState } from "react";
import { HelpCircle, Loader2, Search } from "lucide-react";
import { AlertMessage, StatusBadge } from "@/components/console-primitives";
import { apiFetch, apiMessage, type QueryResponse } from "@/lib/api";

type QueryConsoleProps = {
  workspaceId: string;
  token: string;
};

type QueryHistoryItem = {
  id: string;
  question: string;
  answerState: string;
  auditId: string;
  createdAt: string;
};

const EXAMPLES = [
  "Can customers pay with Pix?",
  "Qual o preco do corte?",
  "What are the business hours?",
  "Existe politica de cancelamento?"
];

export function QueryConsole({ workspaceId, token }: QueryConsoleProps) {
  const [question, setQuestion] = useState("");
  const [maxOutputTokens, setMaxOutputTokens] = useState("512");
  const [includeEvidence, setIncludeEvidence] = useState(true);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [history, setHistory] = useState<QueryHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parsedMaxTokens = useMemo(() => {
    const value = Number(maxOutputTokens);
    return Number.isFinite(value) ? value : 512;
  }, [maxOutputTokens]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) {
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await apiFetch<QueryResponse>(`/workspaces/${workspaceId}/query`, {
        token,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: trimmedQuestion,
          mode: "answer",
          include_evidence: includeEvidence,
          max_output_tokens: clampMaxTokens(parsedMaxTokens)
        })
      });
      setResult(response);
      setHistory((current) => [
        {
          id: response.audit_id,
          question: trimmedQuestion,
          answerState: response.answer_state,
          auditId: response.audit_id,
          createdAt: new Date().toISOString()
        },
        ...current.filter((item) => item.auditId !== response.audit_id)
      ].slice(0, 8));
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="mx-auto max-w-7xl text-slate-950">
      <div className="mb-5">
        <h1 className="text-2xl font-semibold">Knowledge Query</h1>
        <p className="text-sm text-slate-600">
          Ask against published workspace knowledge with evidence, answer state, and audit output.
        </p>
      </div>

      {error ? <AlertMessage tone="error">{error}</AlertMessage> : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-4">
          <form onSubmit={submit} className="rounded border border-slate-200 bg-white p-4">
            <label htmlFor="question" className="text-sm font-medium">
              Question
            </label>
            <div className="mt-2 flex flex-col gap-2 md:flex-row">
              <input
                id="question"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Can customers pay with Pix?"
                maxLength={2000}
                className="h-11 min-w-0 flex-1 rounded border border-slate-300 px-3 text-sm outline-none focus:border-slate-950"
              />
              <button
                type="submit"
                disabled={loading || !question.trim()}
                className="inline-flex h-11 items-center justify-center gap-2 rounded bg-slate-950 px-4 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Search className="h-4 w-4" aria-hidden="true" />}
                Ask
              </button>
            </div>

            <div className="mt-3 grid gap-3 md:grid-cols-[180px_1fr]">
              <label className="text-sm font-medium">
                Max output tokens
                <input
                  type="number"
                  min={64}
                  max={1200}
                  step={64}
                  value={maxOutputTokens}
                  onChange={(event) => setMaxOutputTokens(event.target.value)}
                  className="mt-1 h-10 w-full rounded border border-slate-300 px-3 text-sm font-normal outline-none focus:border-slate-950"
                />
              </label>
              <label className="mt-6 flex h-10 items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={includeEvidence}
                  onChange={(event) => setIncludeEvidence(event.target.checked)}
                  className="h-4 w-4 rounded border-slate-300"
                />
                Include evidence in answer
              </label>
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => setQuestion(example)}
                  className="rounded border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-100"
                >
                  {example}
                </button>
              ))}
            </div>
          </form>

          {loading ? (
            <div className="rounded border border-slate-200 bg-white p-6 text-sm text-slate-600">
              Building answer from published sources...
            </div>
          ) : result ? (
            <QueryResult result={result} />
          ) : (
            <div className="rounded border border-slate-200 bg-white p-6 text-sm text-slate-600">
              No answer yet.
            </div>
          )}
        </div>

        <aside className="space-y-4">
          <HistoryPanel
            history={history}
            onSelect={(item) => setQuestion(item.question)}
          />
          {result ? (
            <>
              <InfoPanel title="Warnings" values={result.warnings} />
              <InfoPanel title="Missing data" values={result.missing_data} />
              <UsagePanel result={result} />
            </>
          ) : null}
        </aside>
      </div>
    </section>
  );
}

function QueryResult({ result }: { result: QueryResponse }) {
  return (
    <section className="space-y-4">
      <div className="rounded border border-slate-200 bg-white p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
          <StatusBadge value={result.answer_state} />
          <span className="text-slate-600">confidence {(result.confidence * 100).toFixed(0)}%</span>
          <span className="break-all text-slate-600">audit {result.audit_id}</span>
          {result.used_unvalidated_data ? <StatusBadge value="unvalidated_data" /> : null}
        </div>
        <p className="whitespace-pre-wrap text-base leading-7">{result.answer}</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <EvidencePanel result={result} />
        <aside className="space-y-4">
          <InfoPanel title="Facts used" values={result.facts_used} />
          <InfoPanel title="Rules used" values={result.rules_used} />
          <InfoPanel title="Sources used" values={result.sources_used} />
        </aside>
      </div>
    </section>
  );
}

function EvidencePanel({ result }: { result: QueryResponse }) {
  return (
    <div className="rounded border border-slate-200 bg-white">
      <div className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        Evidence
      </div>
      {result.evidence.length === 0 ? (
        <div className="flex items-center gap-2 p-4 text-sm text-slate-600">
          <HelpCircle className="h-4 w-4" aria-hidden="true" />
          No evidence returned.
        </div>
      ) : (
        <div className="divide-y divide-slate-100">
          {result.evidence.map((evidence, index) => (
            <article key={`${evidence.evidence_span_id ?? index}`} className="p-4 text-sm">
              <div className="mb-2 flex flex-wrap gap-2 text-xs text-slate-500">
                <span>{evidence.source_name ?? evidence.source_id ?? "unknown source"}</span>
                {evidence.page_number ? <span>page {evidence.page_number}</span> : null}
                {evidence.sheet_name ? <span>sheet {evidence.sheet_name}</span> : null}
                {evidence.row_number ? <span>row {evidence.row_number}</span> : null}
                {evidence.chunk_id ? <span>chunk {evidence.chunk_id.slice(0, 8)}</span> : null}
              </div>
              <blockquote className="border-l-2 border-slate-300 pl-3 leading-6 text-slate-800">
                {evidence.quote ?? "Evidence quote unavailable."}
              </blockquote>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function HistoryPanel({
  history,
  onSelect
}: {
  history: QueryHistoryItem[];
  onSelect: (item: QueryHistoryItem) => void;
}) {
  return (
    <div className="rounded border border-slate-200 bg-white p-4 text-sm">
      <h2 className="font-semibold">Session history</h2>
      {history.length === 0 ? (
        <p className="mt-2 text-slate-600">No questions in this session.</p>
      ) : (
        <div className="mt-3 space-y-2">
          {history.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item)}
              className="block w-full rounded border border-slate-200 bg-slate-50 p-2 text-left hover:bg-slate-100"
            >
              <span className="line-clamp-2 text-slate-800">{item.question}</span>
              <span className="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
                <span>{item.answerState}</span>
                <span>{new Date(item.createdAt).toLocaleTimeString()}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function UsagePanel({ result }: { result: QueryResponse }) {
  return (
    <div className="rounded border border-slate-200 bg-white p-4 text-sm">
      <h2 className="font-semibold">Usage</h2>
      <dl className="mt-3 space-y-2 text-slate-600">
        <Metric label="Provider" value={result.usage.model_provider ?? "deterministic"} />
        <Metric label="Model" value={result.usage.model_name ?? "n/a"} />
        <Metric label="Input" value={String(result.usage.input_tokens)} />
        <Metric label="Output" value={String(result.usage.output_tokens)} />
        <Metric label="Context estimate" value={String(result.usage.context_pack_tokens_estimated)} />
        <Metric label="Estimated cost" value={String(result.usage.estimated_cost)} />
      </dl>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt>{label}</dt>
      <dd className="break-all text-right">{value}</dd>
    </div>
  );
}

function InfoPanel({ title, values }: { title: string; values: string[] }) {
  return (
    <div className="rounded border border-slate-200 bg-white p-4 text-sm">
      <h2 className="font-semibold">{title}</h2>
      {values.length === 0 ? (
        <p className="mt-2 text-slate-600">None</p>
      ) : (
        <ul className="mt-2 space-y-1 text-xs text-slate-600">
          {values.map((value) => (
            <li key={value} className="break-all">
              {value}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function clampMaxTokens(value: number) {
  return Math.min(1200, Math.max(64, Math.round(value)));
}
